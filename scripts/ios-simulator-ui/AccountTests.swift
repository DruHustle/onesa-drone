import XCTest

final class AccountTests: XCTestCase {
    @MainActor private lazy var app = XCUIApplication()
    @MainActor private lazy var safari = XCUIApplication(bundleIdentifier: "com.apple.mobilesafari")
    @MainActor private lazy var authSheet = XCUIApplication(bundleIdentifier: "com.apple.SafariViewService")
    @MainActor private lazy var springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
    private var scenario = ""

    private func checkpoint(_ phase: String) {
        print("ONESA_ACCOUNT_CHECKPOINT \(scenario):\(phase)")
    }

    @MainActor private func waitFor(_ check: () -> Bool, seconds: TimeInterval = 45) -> Bool {
        let deadline = Date().addingTimeInterval(seconds)
        repeat {
            if check() { return true }
            RunLoop.current.run(until: Date().addingTimeInterval(0.25))
        } while Date() < deadline
        return false
    }

    @MainActor private func allowBrowser() {
        for owner in [springboard, app] {
            let button = owner.alerts.buttons["Continue"].firstMatch
            if button.exists && button.isHittable { button.tap(); return }
        }
    }

    @MainActor private func field(_ label: String, in web: XCUIElement) -> XCUIElement {
        let fields = label == "Password" ? web.secureTextFields : web.textFields
        let named = fields[label]
        return named.exists ? named : fields.matching(NSPredicate(format: "label CONTAINS[c] %@", label)).firstMatch
    }

    @MainActor private func login(_ role: String, in web: XCUIElement, factor: String) throws {
        let email = field("Email address", in: web)
        XCTAssertTrue(email.waitForExistence(timeout: 20), "Portal email field")
        email.tap()
        email.typeText(role + "@example.test")
        let password = field("Password", in: web)
        password.tap()
        password.typeText(try XCTUnwrap(ProcessInfo.processInfo.environment["ONESA_FIXTURE_PASSWORD"]))
        checkpoint("credentials-filled")
        let code = field("Authenticator or recovery code", in: web)
        let submit = web.buttons["Continue"].firstMatch
        if role == "admin" && !code.exists {
            submit.tap()
            XCTAssertTrue(code.waitForExistence(timeout: 20), "Portal MFA challenge")
            checkpoint("mfa-visible")
        }
        if role == "admin" {
            code.tap()
            code.typeText(factor)
        }
        submit.tap()
        checkpoint("submitted")
    }

    @MainActor private func inSheet(_ name: String) -> XCUIElement? {
        for surface in [app, authSheet, safari] {
            let web = surface.webViews.firstMatch
            guard web.exists else { continue }
            if name == "Email address" {
                if field(name, in: web).exists { return web }
            } else if web.buttons[name].exists { return web }
        }
        return nil
    }

    @MainActor private func signIn(_ role: String, warm: Bool, factor: String) throws {
        scenario = role + (warm ? ":warm" : ":cold")
        checkpoint("start")
        let address = role + "@example.test"
        if warm {
            // Establish the active central session in Safari independently of the Drone app.
            safari.open(try XCTUnwrap(URL(string: "https://localhost:54843/account")))
            let web = safari.webViews.firstMatch
            XCTAssertTrue(web.waitForExistence(timeout: 30), "Standalone Portal browser")
            checkpoint("browser-ready")
            try login(role, in: web, factor: factor)
            XCTAssertTrue(web.buttons["Sign out of Onesa"].waitForExistence(timeout: 30), "Active Portal browser session")
        }
        app.launch()
        let account = app.buttons["Onesa account"]
        XCTAssertTrue(account.waitForExistence(timeout: 100), "Signed-out Drone planner")
        account.tap()
        app.buttons["Sign in with Onesa"].tap()
        if warm {
            let reuse = "Continue as " + address
            let returned = app.buttons["Open my field planner"]
            XCTAssertTrue(waitFor {
                allowBrowser()
                if let web = inSheet(reuse) { web.buttons[reuse].tap() }
                return returned.exists
            }, "Reused active Portal session without entering credentials")
        } else {
            XCTAssertTrue(waitFor {
                allowBrowser()
                return inSheet("Email address") != nil
            }, "Portal login in system browser")
            let web = try XCTUnwrap(inSheet("Email address"))
            checkpoint("browser-ready")
            try login(role, in: web, factor: factor)
        }
        let identity = app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", address)).firstMatch
        XCTAssertTrue(identity.waitForExistence(timeout: 45), "OS callback returned the requested account")
        checkpoint("identity-returned")
        let assigned = role == "admin" ? "Portal administrator" : "Fixture workspace · operator"
        XCTAssertTrue(app.staticTexts[assigned].exists, "Expected account authority")
        app.terminate()
        app.launch()
        let restored = app.buttons[address]
        XCTAssertTrue(restored.waitForExistence(timeout: 75), "Keychain session survives relaunch")
        checkpoint("keychain-restored")
        restored.tap()
        XCTAssertTrue(app.staticTexts[assigned].waitForExistence(timeout: 15), "Revalidated account authority")
        app.buttons["Sign out of Onesa"].tap()
        XCTAssertTrue(app.staticTexts["Signed out of Onesa."].waitForExistence(timeout: 30), "Confirmed central sign-out")
        checkpoint("central-logout")
        app.terminate()
    }

    @MainActor func testPortalSignInAndSystemCallback() throws {
        continueAfterFailure = false
        let env = ProcessInfo.processInfo.environment
        for role in ["member", "admin"] {
            try signIn(role, warm: false, factor: try XCTUnwrap(env["ONESA_FIXTURE_FACTOR"]))
            try signIn(role, warm: true, factor: try XCTUnwrap(env["ONESA_FIXTURE_SECOND_FACTOR"]))
        }
    }
}

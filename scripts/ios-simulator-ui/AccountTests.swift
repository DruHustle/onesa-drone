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

    @MainActor private func dismissNativeKeyboard() throws {
        var doneTyping: XCUIElement?
        XCTAssertTrue(waitFor({
            for surface in [app, authSheet, safari] where surface.state == .runningForeground {
                let done = surface.buttons["Done"].firstMatch
                if done.exists && done.isHittable { doneTyping = done; return true }
            }
            return false
        }, seconds: 10), "Native browser Done control")
        try XCTUnwrap(doneTyping).tap()
        XCTAssertTrue(waitFor({
            [app, authSheet, safari].filter { $0.state == .runningForeground }.allSatisfy { !$0.keyboards.firstMatch.exists }
        }, seconds: 10), "Native keyboard dismissed before form action")
    }

    @MainActor private func login(_ role: String, in web: XCUIElement, factor: String, remember: Bool = false) throws {
        let email = field("Email address", in: web)
        XCTAssertTrue(email.waitForExistence(timeout: 20), "Portal email field")
        email.tap()
        email.typeText(role + "@example.test")
        let password = field("Password", in: web)
        try dismissNativeKeyboard()
        password.tap()
        password.typeText(try XCTUnwrap(ProcessInfo.processInfo.environment["ONESA_FIXTURE_PASSWORD"]))
        try dismissNativeKeyboard()
        checkpoint("credentials-filled")
        if remember {
            let checkbox = web.checkBoxes["Remember this browser"].firstMatch
            let toggle = web.switches["Remember this browser"].firstMatch
            XCTAssertTrue(waitFor({ checkbox.exists || toggle.exists }, seconds: 10), "Remember browser control")
            let control = checkbox.exists ? checkbox : toggle
            if control.value as? String != "1" { control.tap() }
            XCTAssertEqual(control.value as? String, "1", "Explicit remembered browser session")
        }
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
            try dismissNativeKeyboard()
        }
        submit.tap()
        checkpoint("submitted")
    }

    @MainActor private func inSheet(_ name: String, browserOnly: Bool = false) -> XCUIElement? {
        let owners = browserOnly ? [authSheet, safari] : [app, authSheet, safari]
        for surface in owners where surface.state == .runningForeground {
            let web = surface.webViews.firstMatch
            guard web.exists else { continue }
            if name == "Email address" {
                if field(name, in: web).exists { return web }
            } else if web.buttons[name].exists { return web }
        }
        return nil
    }

    @MainActor private func signIn(_ role: String, warm: Bool, factor: String) async throws {
        scenario = role + (warm ? ":warm" : ":cold")
        checkpoint("start")
        let address = role + "@example.test"
        app.launch()
        if warm {
            XCTAssertTrue(app.staticTexts["Your Onesa session or workspace access has changed. Sign in again."].waitForExistence(timeout: 45), "Expired product session requires real sign-in")
        } else {
            let account = app.buttons["Onesa account"]
            XCTAssertTrue(account.waitForExistence(timeout: 100), "Signed-out Drone planner")
            account.tap()
        }
        app.buttons["Sign in with Onesa"].tap()
        if warm {
            let reuse = "Continue as " + address
            let returned = app.buttons["Open my field planner"]
            let reused = waitFor {
                if returned.exists { return true }
                allowBrowser()
                if returned.exists { return true }
                if let web = inSheet(reuse, browserOnly: true) { web.buttons[reuse].tap() }
                return returned.exists
            }
            XCTAssertTrue(reused, "Reused active Portal session without entering credentials")
        } else {
            XCTAssertTrue(waitFor {
                allowBrowser()
                return inSheet("Email address") != nil
            }, "Portal login in system browser")
            let web = try XCTUnwrap(inSheet("Email address"))
            checkpoint("browser-ready")
            try login(role, in: web, factor: factor, remember: true)
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
        if warm {
            app.buttons["Sign out of Onesa"].tap()
            XCTAssertTrue(app.staticTexts["Signed out of Onesa."].waitForExistence(timeout: 30), "Confirmed central sign-out")
            checkpoint("central-logout")
        } else {
            try await expireProductSession(role)
        }
        app.terminate()
    }

    @MainActor private func expireProductSession(_ role: String) async throws {
        var request = URLRequest(url: try XCTUnwrap(URL(string: "https://127.0.0.1:54844/__onesa_fixture/expire-product-session")))
        request.httpMethod = "POST"
        request.timeoutInterval = 15
        request.setValue(try XCTUnwrap(ProcessInfo.processInfo.environment["ONESA_FIXTURE_CONTROL"]), forHTTPHeaderField: "x-onesa-fixture-control")
        request.setValue(role, forHTTPHeaderField: "x-onesa-fixture-role")
        let (data, response) = try await URLSession.shared.data(for: request)
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200, "Scoped fixture product expiry")
        let receipt = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(receipt["expiredProductSessions"] as? Int, 1, "Exactly one product session expired")
        XCTAssertEqual(receipt["portalSessionRowsUnchanged"] as? Bool, true, "Portal session remains unchanged")
        XCTAssertEqual(receipt["expectedRoleVerified"] as? Bool, true, "Expiry belongs to expected synthetic role")
        XCTAssertEqual(receipt["expectedProductSubjectVerified"] as? Bool, true, "Expiry belongs to expected immutable subject")
    }

    @MainActor func testPortalSignInAndSystemCallback() async throws {
        continueAfterFailure = false
        let env = ProcessInfo.processInfo.environment
        for role in ["member", "admin"] {
            try await signIn(role, warm: false, factor: try XCTUnwrap(env["ONESA_FIXTURE_FACTOR"]))
            try await signIn(role, warm: true, factor: "")
        }
    }
}

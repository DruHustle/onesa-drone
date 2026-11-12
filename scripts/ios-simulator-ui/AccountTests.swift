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

    @MainActor private func signInGeometry(_ stage: String) {
        let button = app.buttons["Sign in with Onesa"]
        guard button.exists else { return }
        let frame = button.frame
        let window = app.frame
        let values: [String: Any] = [
            "x": frame.origin.x, "y": frame.origin.y,
            "width": frame.width, "height": frame.height,
            "exists": button.exists, "enabled": button.isEnabled, "hittable": button.isHittable,
            "centerInWindow": window.contains(CGPoint(x: frame.midX, y: frame.midY))
        ]
        if JSONSerialization.isValidJSONObject(values),
           let data = try? JSONSerialization.data(withJSONObject: values, options: [.sortedKeys]),
           let text = String(data: data, encoding: .utf8) {
            print("ONESA_ACCOUNT_BUTTON \(scenario):\(stage):\(text)")
        }
    }

    @MainActor private func browserFailureState() {
        // Only fixed state names leave the private XCTest log. Never print an
        // element label/value, URL, hierarchy, error description or screenshot.
        // Preserve the failed wait even if a diagnostic OS query also fails.
        checkpoint("browser-wait-failed")
        func observed(_ name: String, _ present: Bool) {
            if present { print("ONESA_ACCOUNT_STATE \(scenario):\(name)") }
        }
        signInGeometry("failure")
        observed("app-foreground", app.state == .runningForeground)
        observed("safari-foreground", safari.state == .runningForeground)
        observed("auth-sheet-foreground", authSheet.state == .runningForeground)
        observed("consent-continue-visible", [springboard, app].contains {
            let button = $0.alerts.buttons["Continue"].firstMatch
            return button.exists && button.isHittable
        })
        let signIn = app.buttons["Sign in with Onesa"]
        observed("sign-in-enabled", signIn.exists && signIn.isEnabled)
        observed("sign-in-disabled", signIn.exists && !signIn.isEnabled)
        observed("contacting-visible", app.staticTexts["Contacting Onesa…"].exists)
        observed("service-unavailable-visible", app.staticTexts["Drone account service is unavailable. Try again when connected."].exists)
        observed("session-rejected-visible", app.staticTexts["Your Onesa session or workspace access has changed. Sign in again."].exists)
        observed("cancelled-visible", app.staticTexts["Sign-in was cancelled. You can start again."].exists)
        observed("invalid-start-visible", app.staticTexts["Invalid sign-in response."].exists)
        observed("network-failure-visible", app.staticTexts.matching(NSPredicate(format: "label CONTAINS[c] %@", "Network request failed")).firstMatch.exists)
        observed("timeout-failure-visible", app.staticTexts.matching(NSPredicate(format: "label ==[c] %@ OR label CONTAINS[c] %@ OR label CONTAINS[c] %@", "Aborted", "timed out", "timeout")).firstMatch.exists)
        observed("tls-failure-visible", app.staticTexts.matching(NSPredicate(format: "label CONTAINS[c] %@ OR label CONTAINS[c] %@ OR label CONTAINS[c] %@", "SSL", "certificate", "secure connection")).firstMatch.exists)
        observed("app-webview-visible", app.state == .runningForeground && app.webViews.firstMatch.exists)
        observed("browser-webview-visible", [authSheet, safari].contains {
            $0.state == .runningForeground && $0.webViews.firstMatch.exists
        })
        observed("email-field-visible", inSheet("Email address") != nil)
    }

    @MainActor private func waitFor(_ check: () -> Bool, seconds: TimeInterval = 45) -> Bool {
        let deadline = Date().addingTimeInterval(seconds)
        repeat {
            if check() { return true }
            RunLoop.current.run(until: Date().addingTimeInterval(0.25))
        } while Date() < deadline
        return false
    }

    @MainActor private func browserConsent() -> XCUIElement? {
        let title = NSPredicate(format: "label CONTAINS[c] %@ AND label CONTAINS[c] %@", "localhost", "sign in")
        for owner in [springboard, app] {
            let alert = owner.alerts.firstMatch
            guard alert.exists, title.evaluate(with: alert) || alert.staticTexts.matching(title).firstMatch.exists else { continue }
            let button = alert.buttons["Continue"].firstMatch
            if button.exists && button.isHittable { return button }
        }
        return nil
    }

    @MainActor private func awaitBrowser(_ ready: @escaping () -> Bool) -> Bool {
        var consent: XCUIElement?
        let presented = {
            consent = self.browserConsent()
            return consent != nil || ready()
        }
        // A WebKit/XCTest snapshot can finish after the deadline. Recheck the
        // live alert once before failing. Rendering Portal gets its own wait
        // after the OS prompt has actually been accepted.
        guard waitFor(presented) || presented() else { return false }
        guard let consent else { return true }
        consent.tap()
        checkpoint("consent-tapped")
        if !consent.waitForNonExistence(timeout: 5), let stillPresented = browserConsent() {
            // The first tap can coincide with presentation. Retry only the
            // same local sign-in alert, without repeating the app's request.
            stillPresented.tap()
        }
        return waitFor(ready)
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

    @MainActor private func receivedCredentialPosts(_ role: String) async throws -> Int {
        var request = URLRequest(url: try XCTUnwrap(URL(string: "https://127.0.0.1:54844/__onesa_fixture/credential-receipt")))
        request.timeoutInterval = 5
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.setValue(try XCTUnwrap(ProcessInfo.processInfo.environment["ONESA_FIXTURE_CONTROL"]), forHTTPHeaderField: "x-onesa-fixture-control")
        request.setValue(role, forHTTPHeaderField: "x-onesa-fixture-role")
        let (data, response) = try await URLSession.shared.data(for: request)
        let status = try XCTUnwrap(response as? HTTPURLResponse).statusCode
        if status == 409 { checkpoint("unexpected-credential-route") }
        if status == 412 { checkpoint("interaction-not-observed") }
        _ = try XCTUnwrap(status == 200 ? true : nil, "Current cold fixture flow is observable")
        let receipt = try JSONDecoder().decode([String: Int].self, from: data)
        return try XCTUnwrap(receipt["credentialPosts"], "Issuer returned a credential count")
    }

    @MainActor private func login(_ role: String, in web: XCUIElement, factor: String, remember: Bool = false) async throws {
        let email = field("Email address", in: web)
        XCTAssertTrue(email.waitForExistence(timeout: 20), "Portal email field")
        email.tap()
        let address = role + "@example.test"
        email.typeText(address)
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
        var submittedCount = 0
        @MainActor func submitForm(requireFactor: Bool = false) async throws {
            // A tap on a disabled or incomplete web form can leave the browser
            // on the same screen without sending a credential request.
            @MainActor func formReady() -> Bool {
                guard submit.exists, submit.isEnabled, submit.isHittable,
                      (email.value as? String) == address,
                      let masked = password.value as? String,
                      !masked.isEmpty, masked != password.placeholderValue else { return false }
                return !requireFactor || (code.value as? String) == factor
            }
            let ready = waitFor(formReady, seconds: 20)
            if !ready { browserFailureState() }
            let prior = try await receivedCredentialPosts(role)
            _ = try XCTUnwrap(prior == submittedCount ? true : nil, "Issuer count matches the current form")
            try XCTUnwrap(ready ? submit : nil, "Filled Portal form is ready to submit").tap()
            let expected = submittedCount + 1
            @MainActor func observedCount() async throws -> Int {
                let deadline = Date().addingTimeInterval(8)
                var count = try await receivedCredentialPosts(role)
                while count == submittedCount && Date() < deadline {
                    try await Task.sleep(nanoseconds: 250_000_000)
                    count = try await receivedCredentialPosts(role)
                }
                return count
            }
            var observed = try await observedCount()
            if observed == submittedCount && formReady() {
                // WebKit can expose a hittable mirrored button whose synthetic
                // tap never reaches the form. Use one visible browser touch only
                // after the independent issuer still reports the prior count.
                let visible = web.frame.intersection(submit.frame)
                if !visible.isEmpty, try await receivedCredentialPosts(role) == submittedCount {
                    let offset = CGVector(dx: visible.midX - web.frame.minX, dy: visible.midY - web.frame.minY)
                    checkpoint("retry-visible-form-touch")
                    web.coordinate(withNormalizedOffset: .zero).withOffset(offset).tap()
                    observed = try await observedCount()
                }
            }
            if observed != expected { browserFailureState() }
            _ = try XCTUnwrap(observed == expected ? true : nil, "Issuer observed exactly one form submission")
            submittedCount = expected
        }
        if role == "admin" && !code.exists {
            try await submitForm()
            XCTAssertTrue(code.waitForExistence(timeout: 20), "Portal MFA challenge")
            checkpoint("mfa-visible")
        }
        if role == "admin" {
            code.tap()
            code.typeText(factor)
            try dismissNativeKeyboard()
        }
        try await submitForm(requireFactor: role == "admin")
        checkpoint("submitted")
    }

    @MainActor private func inSheet(_ name: String, browserOnly: Bool = false, readyForInput: Bool = false) -> XCUIElement? {
        let owners = browserOnly ? [authSheet, safari] : [app, authSheet, safari]
        for surface in owners where surface.state == .runningForeground {
            let web = surface.webViews.firstMatch
            guard web.exists else { continue }
            if name == "Email address" {
                let email = field(name, in: web)
                if email.exists && (!readyForInput || (email.isEnabled && email.isHittable)) { return web }
            } else if web.buttons[name].exists { return web }
        }
        return nil
    }

    @MainActor private func signIn(_ role: String, warm: Bool, factor: String) async throws {
        scenario = role + (warm ? ":warm" : ":cold")
        checkpoint("start")
        let address = role + "@example.test"
        let accountHeading = app.staticTexts["Onesa account"]
        let signInButton = app.buttons["Sign in with Onesa"]
        app.launch()
        if warm {
            XCTAssertTrue(app.staticTexts["Your Onesa session or workspace access has changed. Sign in again."].waitForExistence(timeout: 45), "Expired product session requires real sign-in")
        } else {
            let account = app.buttons["Onesa account"]
            XCTAssertTrue(account.waitForExistence(timeout: 100), "Signed-out Drone planner")
            for attempt in 0..<2 {
                XCTAssertTrue(waitFor({ account.exists && account.isHittable }, seconds: 10), "Account entry is hittable")
                account.tap()
                if waitFor({ accountHeading.exists && signInButton.exists }, seconds: 10) { break }
                // Only retry idempotent navigation if the original planner is
                // still visibly active. Never repeat a sign-in request.
                if attempt == 1 || signInButton.exists || !account.exists || !account.isHittable { break }
            }
        }
        XCTAssertTrue(waitFor({
            accountHeading.exists && signInButton.exists && signInButton.isEnabled && signInButton.isHittable
        }), "Account sign-in is ready")
        checkpoint("account-screen-ready")
        signInGeometry("before")
        signInButton.tap()
        checkpoint("sign-in-tapped")
        if warm {
            let reuse = "Continue as " + address
            let returned = app.buttons["Open my field planner"]
            let reused = awaitBrowser {
                if returned.exists { return true }
                if let web = self.inSheet(reuse, browserOnly: true) { web.buttons[reuse].tap() }
                return returned.exists
            }
            if !reused { browserFailureState() }
            XCTAssertTrue(reused, "Reused active Portal session without entering credentials")
        } else {
            let browserReady = awaitBrowser { self.inSheet("Email address", browserOnly: true, readyForInput: true) != nil }
            if !browserReady { browserFailureState() }
            XCTAssertTrue(browserReady, "Portal login in system browser")
            let web = try XCTUnwrap(inSheet("Email address", browserOnly: true, readyForInput: true))
            checkpoint("browser-ready")
            try await login(role, in: web, factor: factor, remember: true)
        }
        let identity = app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", address)).firstMatch
        let returned = identity.waitForExistence(timeout: 45)
        if !returned { browserFailureState() }
        _ = try XCTUnwrap(returned ? identity : nil, "OS callback returned the requested account")
        checkpoint("identity-returned")
        let assigned = role == "admin" ? "Portal administrator" : "Fixture workspace · operator"
        XCTAssertTrue(app.staticTexts[assigned].exists, "Expected account authority")
        app.terminate()
        app.launch()
        let restored = app.buttons[address]
        let restoredAccount = try XCTUnwrap(restored.waitForExistence(timeout: 75) ? restored : nil,
                                           "Keychain session survives relaunch")
        checkpoint("keychain-restored")
        restoredAccount.tap()
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

import XCTest

final class PlannerTests: XCTestCase {
    @MainActor private lazy var app = XCUIApplication()

    @MainActor private func openTab(_ name: String) {
        let tab = app.descendants(matching: .any)["planner-tab-" + name]
        XCTAssertTrue(tab.waitForExistence(timeout: 10))
        tab.tap()
    }

    @MainActor private func reveal(_ element: XCUIElement) {
        let scroll = app.scrollViews.firstMatch
        XCTAssertTrue(scroll.waitForExistence(timeout: 10))
        if element.exists && element.isHittable { return }
        for _ in 0..<8 {
            scroll.swipeDown()
            if element.exists && element.isHittable { return }
        }
        for _ in 0..<14 {
            scroll.swipeUp()
            if element.exists && element.isHittable { return }
        }
        XCTFail("Expected planner control never appeared on screen: \(element)")
    }

    @MainActor private func capture(_ name: String) throws {
        guard ProcessInfo.processInfo.environment["ONESA_PLANNER_IMAGES"] == "1" else { return }
        let documents = try XCTUnwrap(FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first)
        try app.screenshot().pngRepresentation.write(to: documents.appendingPathComponent(name), options: .atomic)
    }

    @MainActor func testOfflineDraftSurvivesRelaunchAndHardwareStaysLocked() throws {
        continueAfterFailure = false
        app.launch()
        XCTAssertTrue(app.staticTexts["Drone Mission Control"].waitForExistence(timeout: 100))
        XCTAssertTrue(app.staticTexts["Mission planner"].exists)
        XCTAssertTrue(app.staticTexts["SIMULATION ONLY · Physical launch and remote commands disabled"].exists)
        try capture("planner.png")
        openTab("Missions")
        XCTAssertTrue(app.staticTexts["No saved routes yet. Create one under Plan."].waitForExistence(timeout: 10))

        openTab("Plan")
        let example = app.buttons["Load example"]
        reveal(example)
        example.tap()
        let save = app.buttons["Save encrypted draft"]
        reveal(save)
        XCTAssertTrue(save.isEnabled)
        save.tap()
        XCTAssertTrue(app.staticTexts["Example security perimeter"].waitForExistence(timeout: 15))

        app.terminate()
        app.launch()
        XCTAssertTrue(app.staticTexts["Mission planner"].waitForExistence(timeout: 75))
        openTab("Missions")
        let title = app.staticTexts["Example security perimeter"]
        XCTAssertTrue(title.waitForExistence(timeout: 15))
        let open = app.buttons["Open route"]
        reveal(open)
        open.tap()
        XCTAssertTrue(app.staticTexts["Draft loaded. Physical aircraft remains disconnected."].waitForExistence(timeout: 10))
        let name = app.textFields["Mission name"]
        reveal(name)
        XCTAssertEqual(name.value as? String, "Example security perimeter")

        openTab("Aircraft")
        reveal(app.staticTexts["Disconnected"])
        XCTAssertTrue(app.staticTexts["Waypoint dispatch"].exists)
        XCTAssertTrue(app.staticTexts["Disabled"].firstMatch.exists)
        openTab("Video")
        reveal(app.staticTexts["No live feed"])
        try capture("locked-video.png")
    }
}

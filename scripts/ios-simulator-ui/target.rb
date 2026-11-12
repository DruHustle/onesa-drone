# Evaluated by CocoaPods in the generated simulator project. xcodeproj is part
# of the existing CocoaPods installation. Device archives use the ordinary Podfile.
require 'xcodeproj'
require 'fileutils'

ios = File.expand_path('../../frontend/drone/mobile/ios', __dir__)
project_path = File.join(ios, 'OnesaDrone.xcodeproj')
project = Xcodeproj::Project.open(project_path)
app = project.native_targets.find { |target| target.name == 'OnesaDrone' }
raise 'Generated Onesa Drone application target missing' unless app

name = 'OnesaDroneSimulatorUI'
unless project.native_targets.any? { |target| target.name == name }
  target = project.new_target(:ui_test_bundle, name, :ios, app.deployment_target)
  target.add_dependency(app)
  target.build_configurations.each do |config|
    config.build_settings.merge!(
      'PRODUCT_BUNDLE_IDENTIFIER' => 'eu.onesa.drone.simulator-ui',
      'PRODUCT_NAME' => '$(TARGET_NAME)',
      'TEST_TARGET_NAME' => app.name,
      'GENERATE_INFOPLIST_FILE' => 'YES',
      'SWIFT_VERSION' => '5.0',
      'SUPPORTED_PLATFORMS' => 'iphonesimulator'
    )
  end
  source_path = File.join(ios, name)
  FileUtils.mkdir_p(source_path)
  group = project.main_group.new_group(name, name)
  %w[PlannerTests.swift AccountTests.swift].each do |file|
    FileUtils.cp(File.join(__dir__, file), source_path)
    target.add_file_references([group.new_file(file)])
  end
  attributes = project.root_object.attributes['TargetAttributes'] ||= {}
  attributes[target.uuid] = { 'TestTargetID' => app.uuid }
  project.save
  scheme = Xcodeproj::XCScheme.new
  scheme.configure_with_targets(app, target, launch_target: true)
  scheme.save_as(project_path, name)
end

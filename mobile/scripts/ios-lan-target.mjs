import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { IOSConfig } = require('expo/config-plugins');

export function installLANTestTarget(ios, appName, source) {
  const name = 'LedovaNetworkTests';
  const file = path.join(ios, `${appName}.xcodeproj/project.pbxproj`);
  const project = IOSConfig.XcodeUtils.getPbxproj(path.dirname(ios));
  const app = project.getFirstTarget();
  assert.equal(app.firstTarget.name.replaceAll('"', ''), appName);
  const dependencies = [...app.firstTarget.dependencies];
  const target = project.addTarget(name, 'unit_test_bundle', name, 'org.example.ledova.networktests');
  app.firstTarget.dependencies = dependencies;
  project.hash.project.objects.PBXTargetDependency ??= {};
  project.hash.project.objects.PBXContainerItemProxy ??= {};
  project.addTargetDependency(target.uuid, [app.uuid]);
  assert.equal(target.pbxNativeTarget.dependencies.length, 1);
  project.addBuildPhase([], 'PBXSourcesBuildPhase', 'Sources', target.uuid);
  project.addBuildPhase([], 'PBXFrameworksBuildPhase', 'Frameworks', target.uuid);
  const group = project.addPbxGroup([], name, name);
  project.addToPbxGroup(group.uuid, project.getFirstProject().firstProject.mainGroup);
  project.addSourceFile(`${name}.m`, { target: target.uuid }, group.uuid);
  const list = project.pbxXCConfigurationList()[target.pbxNativeTarget.buildConfigurationList];
  for (const config of list.buildConfigurations) {
    const settings = project.pbxXCBuildConfigurationSection()[config.value].buildSettings;
    delete settings.INFOPLIST_FILE;
    Object.assign(settings, {
      GENERATE_INFOPLIST_FILE: 'YES',
      TEST_HOST: `"$(BUILT_PRODUCTS_DIR)/${appName}.app/${appName}"`,
      BUNDLE_LOADER: '"$(TEST_HOST)"',
      IPHONEOS_DEPLOYMENT_TARGET: '15.1',
      TARGETED_DEVICE_FAMILY: '"1,2"',
      CLANG_ENABLE_MODULES: 'YES',
      CLANG_ENABLE_OBJC_ARC: 'YES',
      SWIFT_VERSION: '5.0',
      FRAMEWORK_SEARCH_PATHS: ['"$(inherited)"', '"$(PLATFORM_DIR)/Developer/Library/Frameworks"'],
      OTHER_LDFLAGS: ['"$(inherited)"', '"-framework"', 'XCTest'],
    });
  }
  fs.writeFileSync(file, project.writeSync());
  fs.mkdirSync(path.join(ios, name));
  fs.copyFileSync(source, path.join(ios, name, `${name}.m`));
  const podfile = path.join(ios, 'Podfile');
  const podSource = fs.readFileSync(podfile, 'utf8');
  const hook = '  post_install do |installer|';
  assert.equal(podSource.split(hook).length, 2);
  fs.writeFileSync(
    podfile,
    podSource.replace(hook, `  target '${name}' do\n    inherit! :search_paths\n  end\n\n${hook}`),
  );
  const schemeFile = path.join(ios, `${appName}.xcodeproj/xcshareddata/xcschemes/${appName}.xcscheme`);
  const scheme = fs.readFileSync(schemeFile, 'utf8');
  const testables = /<Testables>[\s\S]*?<\/Testables>/g;
  assert.equal([...scheme.matchAll(testables)].length, 1);
  fs.writeFileSync(
    schemeFile,
    scheme.replace(
      testables,
      `<Testables><TestableReference skipped="NO"><BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="${target.uuid}" BuildableName="${name}.xctest" BlueprintName="${name}" ReferencedContainer="container:${appName}.xcodeproj" /></TestableReference></Testables>`,
    ),
  );
  return { app: app.uuid, test: target.uuid };
}

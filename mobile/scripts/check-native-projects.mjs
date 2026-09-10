import { prepareCamera } from './prepare-camera-android.mjs';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { XML, IOSConfig } = require('expo/config-plugins');
const plist = require('@expo/plist').default;
const root = path.resolve(process.argv[2] || path.join(import.meta.dirname, '..'));
const platform = process.argv[3] || 'all';

async function xml(file) {
  return XML.parseXMLAsync(fs.readFileSync(path.join(root, file), 'utf8'));
}

if (platform !== 'ios') {
  prepareCamera('verify');
  const manifest = await xml('android/app/src/main/AndroidManifest.xml');
  const application = manifest.manifest.application[0].$;
  assert.equal(application['android:usesCleartextTraffic'], 'false');
  assert.equal(application['android:networkSecurityConfig'], '@xml/ledova_network_security_config');
  assert.equal(application['android:fullBackupContent'], '@xml/secure_store_backup_rules');
  assert.equal(application['android:dataExtractionRules'], '@xml/secure_store_data_extraction_rules');
  const main = (await xml('android/app/src/main/res/xml/ledova_network_security_config.xml'))[
    'network-security-config'
  ];
  assert.equal(main['base-config'][0].$.cleartextTrafficPermitted, 'false');
  assert.equal(main['domain-config'], undefined);
  const debug = (await xml('android/app/src/debug/res/xml/ledova_network_security_config.xml'))[
    'network-security-config'
  ];
  assert.equal(debug['base-config'][0].$.cleartextTrafficPermitted, 'false');
  const domains = debug['domain-config'][0].domain;
  const expected = ['localhost', '127.0.0.1', '::1', '10.0.2.2', process.env.EXPO_PUBLIC_DEV_API_HOST].filter(Boolean);
  assert.deepEqual(domains.map((domain) => domain._).sort(), [...new Set(expected)].sort());
  assert.ok(domains.every((domain) => domain.$.includeSubdomains === 'false'));
  const backupRoot = path.join(root, 'node_modules/expo-secure-store/android/src/main/res/xml');
  const backup = await XML.parseXMLAsync(
    fs.readFileSync(path.join(backupRoot, 'secure_store_backup_rules.xml'), 'utf8'),
  );
  assert.ok(
    backup['full-backup-content'].exclude.some(({ $ }) => $.domain === 'sharedpref' && $.path === 'SecureStore'),
  );
  const extraction = await XML.parseXMLAsync(
    fs.readFileSync(path.join(backupRoot, 'secure_store_data_extraction_rules.xml'), 'utf8'),
  );
  for (const mode of ['cloud-backup', 'device-transfer']) {
    assert.ok(
      extraction['data-extraction-rules'][mode][0].exclude.some(
        ({ $ }) => $.domain === 'sharedpref' && $.path === 'SecureStore',
      ),
    );
  }
  const wrapper = fs.readFileSync(path.join(root, 'android/gradle/wrapper/gradle-wrapper.properties'), 'utf8');
  assert.match(wrapper, /distributionSha256Sum=bd71102213493060956ec229d946beee57158dbd89d0e62b91bca0fa2c5f3531/);
  const native = fs.readFileSync(
    path.join(root, 'android/app/src/main/java/org/example/ledova/MainApplication.kt'),
    'utf8',
  );
  assert.ok(native.indexOf('setOkHttpClientFactory') >= 0);
  assert.ok(native.indexOf('setOkHttpClientFactory') < native.indexOf('loadReactNative(this)'));
  assert.match(native, /\.followRedirects\(false\)/);
  assert.match(native, /\.followSslRedirects\(false\)/);
}

if (platform !== 'android') {
  const source = IOSConfig.Paths.getSourceRoot(root);
  const release = plist.parse(fs.readFileSync(path.join(source, 'Info.plist'), 'utf8'));
  const debug = plist.parse(fs.readFileSync(path.join(source, 'Info-Debug.plist'), 'utf8'));
  assert.deepEqual(
    { ...release.NSAppTransportSecurity },
    {
      NSAllowsArbitraryLoads: false,
      NSAllowsLocalNetworking: false,
      NSAllowsArbitraryLoadsInWebContent: false,
    },
  );
  assert.equal(release.LedovaDevelopmentHTTPHosts, undefined);
  assert.equal(debug.NSAppTransportSecurity.NSAllowsLocalNetworking, true);
  assert.ok(debug.LedovaDevelopmentHTTPHosts.includes('localhost'));
  const project = IOSConfig.XcodeUtils.getPbxproj(root);
  const builds = Object.values(project.pbxXCBuildConfigurationSection()).filter(
    (build) => build.buildSettings?.INFOPLIST_FILE,
  );
  assert.ok(builds.length >= 2);
  for (const build of builds) {
    assert.ok(build.buildSettings.INFOPLIST_FILE.endsWith(build.name === 'Debug' ? 'Info-Debug.plist' : 'Info.plist'));
    assert.equal(build.buildSettings.IPHONEOS_DEPLOYMENT_TARGET, '15.1');
  }
  const native = fs.readFileSync(path.join(source, 'LedovaHTTPRequestHandler.m'), 'utf8');
  assert.match(native, /completionHandler\(nil\)/);
  assert.match(native, /#if DEBUG/);
  assert.match(native, /NSURLErrorAppTransportSecurityRequiresSecureConnection/);
  const manifest = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
  assert.ok(
    manifest.codegenConfig.ios.modulesConformingToProtocol.RCTURLRequestHandler.includes('LedovaHTTPRequestHandler'),
  );
}

console.log(`Generated ${platform} transport, backup and native registration controls passed.`);

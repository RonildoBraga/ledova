const fs = require('node:fs');
const path = require('node:path');
const { isIPv4 } = require('node:net');
const {
  withAndroidManifest,
  withMainApplication,
  withXcodeProject,
  withInfoPlist,
  withFinalizedMod,
  IOSConfig,
} = require('expo/config-plugins');
const plist = require('@expo/plist').default;

function developmentHosts() {
  const hosts = ['localhost', '127.0.0.1', '::1', '10.0.2.2'];
  const host = process.env.EXPO_PUBLIC_DEV_API_HOST;
  if (host) {
    const [first, second] = host.split('.').map(Number);
    const privateIP =
      first === 10 || (first === 172 && second >= 16 && second <= 31) || (first === 192 && second === 168);
    if (!isIPv4(host) || !privateIP) throw new Error('EXPO_PUBLIC_DEV_API_HOST must be one private IPv4 address.');
    hosts.push(host);
  }
  return [...new Set(hosts)];
}

module.exports = function withMobileSecurity(config) {
  const hosts = developmentHosts();
  config = withAndroidManifest(config, (config) => {
    const application = config.modResults.manifest.application[0].$;
    application['android:usesCleartextTraffic'] = 'false';
    application['android:networkSecurityConfig'] = '@xml/ledova_network_security_config';
    return config;
  });
  config = withMainApplication(config, (config) => {
    const marker = '    super.onCreate()';
    const factory = 'com.facebook.react.modules.network.OkHttpClientProvider.setOkHttpClientFactory';
    if (!config.modResults.contents.includes(factory)) {
      if (!config.modResults.contents.includes(marker)) throw new Error('Cannot install the Android HTTP policy.');
      config.modResults.contents = config.modResults.contents.replace(
        marker,
        `${marker}
    ${factory} {
      com.facebook.react.modules.network.OkHttpClientProvider.createClientBuilder()
        .followRedirects(false)
        .followSslRedirects(false)
        .build()
    }`,
      );
    }
    return config;
  });
  config = withFinalizedMod(config, [
    'android',
    async (config) => {
      const source = path.join(config.modRequest.platformProjectRoot, 'app', 'src');
      for (const variant of ['main', 'debug']) {
        const directory = path.join(source, variant, 'res', 'xml');
        fs.mkdirSync(directory, { recursive: true });
        const domains =
          variant === 'debug'
            ? `\n  <domain-config cleartextTrafficPermitted="true">\n${hosts.map((host) => `    <domain includeSubdomains="false">${host}</domain>`).join('\n')}\n  </domain-config>`
            : '';
        fs.writeFileSync(
          path.join(directory, 'ledova_network_security_config.xml'),
          `<?xml version="1.0" encoding="utf-8"?>\n<network-security-config>\n  <base-config cleartextTrafficPermitted="false"/>${domains}\n</network-security-config>\n`,
        );
      }
      const wrapper = path.join(
        config.modRequest.platformProjectRoot,
        'gradle',
        'wrapper',
        'gradle-wrapper.properties',
      );
      const properties = fs.readFileSync(wrapper, 'utf8');
      if (!properties.includes('gradle-8.14.3-bin.zip'))
        throw new Error('Review the Gradle distribution before updating its checksum.');
      if (!properties.includes('distributionSha256Sum=')) {
        fs.appendFileSync(
          wrapper,
          '\ndistributionSha256Sum=bd71102213493060956ec229d946beee57158dbd89d0e62b91bca0fa2c5f3531\n',
        );
      }
      return config;
    },
  ]);
  config = withInfoPlist(config, (config) => {
    config.modResults.NSAppTransportSecurity = {
      NSAllowsArbitraryLoads: false,
      NSAllowsLocalNetworking: false,
      NSAllowsArbitraryLoadsInWebContent: false,
    };
    delete config.modResults.LedovaDevelopmentHTTPHosts;
    return config;
  });
  config = withXcodeProject(config, (config) => {
    const project = config.modResults;
    const name = IOSConfig.XcodeUtils.getProjectName(config.modRequest.projectRoot);
    for (const build of Object.values(project.pbxXCBuildConfigurationSection())) {
      if (!build.buildSettings?.INFOPLIST_FILE) continue;
      build.buildSettings.INFOPLIST_FILE = `${name}/${build.name === 'Debug' ? 'Info-Debug' : 'Info'}.plist`;
    }
    const filepath = `${name}/LedovaHTTPRequestHandler.m`;
    if (!project.hasFile(filepath)) {
      IOSConfig.XcodeUtils.addBuildSourceFileToGroup({ filepath, groupName: name, project });
    }
    return config;
  });
  return withFinalizedMod(config, [
    'ios',
    async (config) => {
      const source = IOSConfig.Paths.getSourceRoot(config.modRequest.projectRoot);
      const release = { ...config.ios.infoPlist };
      delete release.LedovaDevelopmentHTTPHosts;
      const debug = {
        ...release,
        NSAppTransportSecurity: {
          ...release.NSAppTransportSecurity,
          NSAllowsLocalNetworking: true,
        },
        LedovaDevelopmentHTTPHosts: hosts,
      };
      fs.writeFileSync(path.join(source, 'Info.plist'), plist.build(release));
      fs.writeFileSync(path.join(source, 'Info-Debug.plist'), plist.build(debug));
      fs.copyFileSync(
        path.join(__dirname, 'native', 'LedovaHTTPRequestHandler.m'),
        path.join(source, 'LedovaHTTPRequestHandler.m'),
      );
      return config;
    },
  ]);
};

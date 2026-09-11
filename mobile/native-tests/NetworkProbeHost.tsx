import { registerRootComponent } from 'expo';
import { Text, View } from 'react-native';

function NetworkProbeHost() {
  return (
    <View>
      <Text>Native network probe</Text>
    </View>
  );
}

registerRootComponent(NetworkProbeHost);

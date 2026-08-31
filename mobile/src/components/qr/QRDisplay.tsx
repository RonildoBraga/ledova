import React from 'react';
import { View, Text } from 'react-native';
import QRCode from 'react-native-qrcode-svg';
import { useAppTheme, useThemedStyles } from '../../contexts';

interface QRDisplayProps {
  data: string | Buffer;
  size?: number;
  isUR?: boolean;
}

export function QRDisplay({ data, size = 300, isUR = false }: QRDisplayProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    container: {
      backgroundColor: theme.colors.utility.white,
      padding: theme.spacing.lg,
      borderRadius: theme.borderRadius.lg,
      alignItems: 'center',
      justifyContent: 'center',
    },
    hint: {
      marginTop: theme.spacing.sm,
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.subtle,
      textAlign: 'center',
    },
  }));
  let qrValue: string;

  if (typeof data === 'string') {
    qrValue = data;
  } else if (Buffer.isBuffer(data)) {
    qrValue = data.toString('hex');
  } else {
    qrValue = String(data);
  }

  const isLongData = qrValue.length > 600;
  const effectiveSize = isLongData ? Math.max(size, 320) : size;

  return (
    <View style={styles.container}>
      <QRCode value={qrValue} size={effectiveSize} backgroundColor="white" color="black" ecl="L" quietZone={10} />
      {isUR && isLongData && <Text style={styles.hint}>Hold device steady while scanning</Text>}
    </View>
  );
}

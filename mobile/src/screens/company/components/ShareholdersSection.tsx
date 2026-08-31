import React, { useState } from 'react';
import { View, Text, TouchableOpacity } from 'react-native';
import { UsersThreeIcon, CopyIcon } from 'phosphor-react-native';
import * as Clipboard from 'expo-clipboard';
import { useAppTheme, useThemedStyles } from '../../../contexts';

function shortenAddress(address: string) {
  if (address.length <= 14) return address;
  return `${address.slice(0, 6)}...${address.slice(-4)}`;
}

interface Holder {
  address: string;
  name: string | null;
  totalBalance: number;
  tokens: Array<{ name: string; symbol: string; balance: number; percentage: number }>;
}

interface ShareholdersSectionProps {
  holders: Holder[];
  deployedTokens: Array<{ uuid: string; name: string; symbol: string }>;
}

export function ShareholdersSection({ holders, deployedTokens }: ShareholdersSectionProps) {
  const theme = useAppTheme();
  const styles = useStyles();
  const [copiedAddress, setCopiedAddress] = useState<string | null>(null);

  const handleCopy = async (address: string) => {
    await Clipboard.setStringAsync(address);
    setCopiedAddress(address);
    setTimeout(() => setCopiedAddress(null), 2000);
  };

  if (holders.length === 0) {
    return (
      <View style={styles.emptyState}>
        <UsersThreeIcon size={32} color={theme.colors.text.muted} weight="regular" />
        <Text style={styles.emptyTitle}>No Shareholders</Text>
        <Text style={styles.emptySubtitle}>
          {deployedTokens.length === 0
            ? 'Deploy a token to start tracking shareholders.'
            : 'No shares have been issued yet.'}
        </Text>
      </View>
    );
  }

  return (
    <>
      {holders.map((holder, index) => (
        <React.Fragment key={holder.address}>
          <View style={styles.holderRow}>
            <View style={styles.holderInfo}>
              <View style={styles.holderHeader}>
                {holder.name ? <Text style={styles.holderName}>{holder.name}</Text> : null}
                <TouchableOpacity style={styles.addressRow} onPress={() => handleCopy(holder.address)}>
                  <Text style={styles.holderAddress}>{shortenAddress(holder.address)}</Text>
                  <CopyIcon
                    size={12}
                    color={copiedAddress === holder.address ? theme.colors.interactive.active : theme.colors.text.muted}
                    weight="regular"
                  />
                </TouchableOpacity>
              </View>
              <View style={styles.tokenBreakdown}>
                {holder.tokens.map((t) => (
                  <View key={t.symbol} style={styles.tokenTag}>
                    <Text style={styles.tokenTagText}>
                      {t.symbol}: {t.balance.toLocaleString()} ({t.percentage.toFixed(1)}%)
                    </Text>
                  </View>
                ))}
              </View>
            </View>
            <Text style={styles.holderBalance}>{holder.totalBalance.toLocaleString()}</Text>
          </View>
          {index < holders.length - 1 && <View style={styles.divider} />}
        </React.Fragment>
      ))}
    </>
  );
}

function useStyles() {
  return useThemedStyles((theme) => ({
    emptyState: {
      alignItems: 'center' as const,
      paddingVertical: theme.spacing.md,
      gap: theme.spacing.sm,
    },
    emptyTitle: {
      fontSize: theme.fontSize.base,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
    },
    emptySubtitle: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      textAlign: 'center' as const,
    },
    holderRow: {
      flexDirection: 'row' as const,
      justifyContent: 'space-between' as const,
      alignItems: 'flex-start' as const,
      paddingVertical: theme.spacing.sm,
      paddingHorizontal: theme.spacing.xs,
    },
    holderInfo: { flex: 1, gap: 6 },
    holderHeader: { gap: 2 },
    holderName: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
    },
    addressRow: {
      flexDirection: 'row' as const,
      alignItems: 'center' as const,
      gap: 4,
    },
    holderAddress: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
      fontFamily: 'monospace',
    },
    tokenBreakdown: {
      flexDirection: 'row' as const,
      flexWrap: 'wrap' as const,
      gap: 4,
    },
    tokenTag: {
      backgroundColor: theme.colors.surface.tertiary,
      borderRadius: 4,
      paddingHorizontal: 6,
      paddingVertical: 2,
    },
    tokenTagText: {
      fontSize: 10,
      color: theme.colors.text.muted,
    },
    holderBalance: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.bold,
      color: theme.colors.text.primary,
      fontVariant: ['tabular-nums'],
    },
    divider: {
      height: 1,
      backgroundColor: theme.colors.border.default,
    },
  }));
}

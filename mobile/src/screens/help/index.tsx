import React from 'react';
import { View, Text, ScrollView, Linking } from 'react-native';
import { EnvelopeSimpleIcon, InfoIcon, QuestionIcon, FileTextIcon } from 'phosphor-react-native';
import { GradientBackground } from '../../components/GradientBackground';
import { ContactCard } from './components/ContactCard';
import { PUBLIC_LINKS, SUPPORT_EMAIL } from '../../config/publicLinks';
import { useAppTheme, useThemedStyles } from '../../contexts';
import appJson from '../../../app.json';

const APP_VERSION = appJson.expo.version;
const CURRENT_YEAR = new Date().getFullYear();

export function HelpScreen() {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    container: {
      flex: 1,
    },
    contentContainer: {
      padding: theme.spacing.md,
      paddingBottom: theme.spacing.xxl,
    },
    cardsContainer: {
      gap: theme.spacing.md,
    },
    aboutContainer: {
      marginTop: theme.spacing.xs,
      gap: theme.spacing.xs,
    },
    aboutText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
    },
    legalContainer: {
      marginTop: theme.spacing.xs,
      gap: theme.spacing.sm,
    },
    legalLink: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.info.light,
      fontWeight: theme.fontWeight.medium,
    },
  }));
  const handleEmailPress = () => {
    Linking.openURL(`mailto:${SUPPORT_EMAIL}`);
  };

  const handleVisitHelpCenter = () => {
    Linking.openURL(PUBLIC_LINKS.helpCenter);
  };

  const handleTermsOfService = () => {
    Linking.openURL(PUBLIC_LINKS.termsOfService);
  };

  const handlePrivacyPolicy = () => {
    Linking.openURL(PUBLIC_LINKS.privacyPolicy);
  };

  return (
    <GradientBackground>
      <ScrollView style={styles.container} contentContainerStyle={styles.contentContainer}>
        {/* Contact Options */}
        <View style={styles.cardsContainer}>
          {/* Email Support */}
          {SUPPORT_EMAIL ? (
            <ContactCard
              icon={<EnvelopeSimpleIcon />}
              title="Deployment Support"
              description="Contact the support channel configured by this deployment's owner."
              actionLabel={SUPPORT_EMAIL}
              actionType="link"
              onAction={handleEmailPress}
            />
          ) : null}

          {/* Help Center */}
          <ContactCard
            icon={<QuestionIcon />}
            title="Help Center"
            description="Browse the reference documentation served by the configured marketing site."
            actionLabel="Visit Help Center"
            actionType="link"
            onAction={handleVisitHelpCenter}
          />

          {/* Legal */}
          <ContactCard icon={<FileTextIcon />} title="Legal" description="Review our terms and policies.">
            <View style={styles.legalContainer}>
              <Text style={styles.legalLink} onPress={handleTermsOfService}>
                Terms of Service
              </Text>
              <Text style={styles.legalLink} onPress={handlePrivacyPolicy}>
                Privacy Policy
              </Text>
            </View>
          </ContactCard>

          {/* About */}
          <ContactCard icon={<InfoIcon />} title="About" description="">
            <View style={styles.aboutContainer}>
              <Text style={styles.aboutText}>Version {APP_VERSION}</Text>
              <Text style={styles.aboutText}>© {CURRENT_YEAR} Ledova contributors</Text>
              <Text style={styles.aboutText}>Licensed under Apache-2.0.</Text>
            </View>
          </ContactCard>
        </View>
      </ScrollView>
    </GradientBackground>
  );
}

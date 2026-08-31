import React from 'react';
import { TouchableOpacity, View, Text } from 'react-native';
import { ListIcon, BellIcon } from 'phosphor-react-native';
import { Header, getHeaderTitle } from '@react-navigation/elements';
import { useAppTheme } from '../../contexts';
import { useDrawer } from '../DrawerContext';

type ThemeParam = ReturnType<typeof useAppTheme>;

interface MainHeaderProps {
  theme: ThemeParam;
  onNotifications: () => void;
  unreadCount?: number;
}

function DrawerToggleButton() {
  const theme = useAppTheme();
  const { openDrawer } = useDrawer();
  return (
    <TouchableOpacity
      onPress={openDrawer}
      style={{
        width: 44,
        height: 44,
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <ListIcon size={theme.icon.sizes.lg} color={theme.colors.text.muted} weight={theme.icon.weights.regular} />
    </TouchableOpacity>
  );
}

export function MainHeader({ theme, onNotifications, unreadCount = 0 }: MainHeaderProps) {
  const badgeText = unreadCount > 99 ? '99+' : String(unreadCount);

  return {
    headerLeft: () => <DrawerToggleButton />,
    headerRight: () => (
      <TouchableOpacity
        onPress={onNotifications}
        style={{
          width: 44,
          height: 44,
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <BellIcon size={theme.icon.sizes.lg} color={theme.colors.text.muted} weight={theme.icon.weights.regular} />
        {unreadCount > 0 && (
          <View
            style={{
              position: 'absolute',
              top: 4,
              right: 2,
              minWidth: 18,
              height: 18,
              borderRadius: 9,
              backgroundColor: theme.colors.status.error.icon,
              alignItems: 'center',
              justifyContent: 'center',
              paddingHorizontal: 4,
            }}
          >
            <Text
              style={{
                fontSize: 10,
                fontWeight: 'bold',
                color: theme.colors.utility.white,
              }}
            >
              {badgeText}
            </Text>
          </View>
        )}
      </TouchableOpacity>
    ),
    headerLeftContainerStyle: { paddingLeft: theme.spacing.md, paddingBottom: theme.spacing.xs },
    headerRightContainerStyle: { paddingRight: theme.spacing.md, paddingBottom: theme.spacing.xs },
  };
}

export function getMainHeaderStyle(theme: ThemeParam) {
  return {
    headerShown: true,
    header: ({
      options,
      route,
      back,
    }: {
      options: Record<string, unknown>;
      route: { name: string };
      back?: { title: string | undefined; href: string | undefined };
    }) => (
      <Header
        title={getHeaderTitle(options as Parameters<typeof getHeaderTitle>[0], route.name)}
        headerStyle={{ backgroundColor: theme.colors.surface.raised }}
        headerTintColor={theme.colors.text.primary}
        headerTitleStyle={{
          fontWeight: theme.fontWeight.semibold as '600',
          fontSize: theme.fontSize.lg,
        }}
        headerShadowVisible={false}
        headerLeft={options.headerLeft as HeaderLeftType}
        headerRight={options.headerRight as HeaderRightType}
        headerLeftContainerStyle={options.headerLeftContainerStyle as Record<string, unknown>}
        headerRightContainerStyle={options.headerRightContainerStyle as Record<string, unknown>}
        back={back}
      />
    ),
  };
}

type HeaderLeftType = ((props: { canGoBack?: boolean }) => React.ReactNode) | undefined;
type HeaderRightType = ((props: { canGoBack: boolean }) => React.ReactNode) | undefined;

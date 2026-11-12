import React, { useCallback, useEffect, useRef, useState } from "react";
import { AppState, Linking, ScrollView, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import * as SecureStore from "expo-secure-store";
import * as WebBrowser from "expo-web-browser";
import { Body, Button, Panel, styles } from "./field-ui.jsx";
import { SESSION_KEY, requestAccount, signIn } from "./mobile-account.mjs";

export default function AccountHome({ colors, children }) {
  const [account, setAccount] = useState(null);
  const [initialized, setInitialized] = useState(false);
  const [opened, setOpened] = useState(false);
  const [locked, setLocked] = useState(true);
  const [working, setWorking] = useState(false);
  const [notice, setNotice] = useState("");
  const revision = useRef(0);
  const workingRef = useRef(false);
  const refresh = useCallback(async () => {
    const attempt = ++revision.current;
    try {
      const session = await SecureStore.getItemAsync(SESSION_KEY);
      const profile = session
        ? await requestAccount("/account", { session })
        : null;
      if (attempt !== revision.current) return;
      if (profile && !/^[a-f0-9]{64}$/.test(profile.storage_scope))
        throw Error("Invalid account response.");
      setAccount(profile);
      setInitialized(true);
      setLocked(false);
    } catch (error) {
      if (attempt !== revision.current) return;
      setLocked(true);
      setOpened(true);
      setNotice(
        "Reconnect to verify your Onesa account, or sign out to use the device planner.",
      );
      if (error.status === 401 || error.status === 403) {
        await SecureStore.deleteItemAsync(SESSION_KEY);
        if (attempt !== revision.current) return;
        setLocked(false);
        setAccount(null);
        setInitialized(true);
        setNotice(error.message);
      }
    }
  }, []);
  useEffect(() => {
    refresh();
    const sub = AppState.addEventListener("change", (state) => {
      if (workingRef.current) return;
      if (state === "active") refresh();
      else {
        revision.current++;
        setLocked(true);
      }
    });
    const timer = setInterval(() => {
      if (!workingRef.current && AppState.currentState === "active") refresh();
    }, 30000);
    return () => {
      revision.current++;
      sub.remove();
      clearInterval(timer);
    };
  }, [refresh]);

  async function act(action) {
    if (workingRef.current) return;
    workingRef.current = true;
    ++revision.current;
    setWorking(true);
    setNotice("");
    try {
      await action();
    } catch (error) {
      setNotice(error.message || "Account service unavailable. Try again.");
    } finally {
      setWorking(false);
      workingRef.current = false;
    }
  }
  async function login() {
    const session = await signIn(WebBrowser.openAuthSessionAsync);
    await SecureStore.setItemAsync(SESSION_KEY, session, {
      keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
    });
    setLocked(true);
    await refresh();
  }
  async function logout() {
    setLocked(true);
    const session = await SecureStore.getItemAsync(SESSION_KEY);
    await SecureStore.deleteItemAsync(SESSION_KEY);
    setAccount(null);
    setInitialized(true);
    setLocked(false);
    let confirmed = false;
    try {
      if (session)
        confirmed = (
          await requestAccount("/logout", { session, method: "POST" })
        ).central_signed_out;
    } catch {
      /* Local credentials have already been removed. */
    } finally {
      setNotice(
        confirmed
          ? "Signed out of Onesa."
          : "Signed out on this device. Sign-out from other apps is unconfirmed.",
      );
    }
  }
  const showAccount = opened || locked;
  return (
    <>
      {initialized && (
        <View
          style={{ flex: 1, display: showAccount ? "none" : "flex" }}
          accessibilityElementsHidden={showAccount}
          importantForAccessibility={
            showAccount ? "no-hide-descendants" : "auto"
          }
        >
          {children(account, () => setOpened(true))}
        </View>
      )}
      {showAccount && (
        <SafeAreaView style={[styles.root, { backgroundColor: colors.canvas }]}>
          <ScrollView contentContainerStyle={styles.content}>
            <Text
              accessibilityRole="header"
              style={[styles.title, { color: colors.text }]}
            >
              Onesa account
            </Text>
            <Panel colors={colors}>
              {account && !locked ? (
                <>
                  <Body colors={colors}>
                    {account.name} · {account.email}
                  </Body>
                  {account.global_admin && (
                    <Body colors={colors}>Portal administrator</Body>
                  )}
                  {account.workspaces.map((w) => (
                    <Body key={w.id} colors={colors}>
                      {w.name} · {w.role}
                    </Body>
                  ))}
                  {!account.workspaces.length && (
                    <Body colors={colors}>
                      Ask an administrator for a Drone workspace.
                    </Body>
                  )}
                  <Button
                    colors={colors}
                    disabled={working}
                    onPress={() => setOpened(false)}
                  >
                    Open my field planner
                  </Button>
                </>
              ) : (
                <>
                  <Body colors={colors}>
                    Use your existing Portal account for your private field
                    planner and Drone workspaces.
                  </Body>
                  <Button
                    colors={colors}
                    disabled={working || locked}
                    onPress={() => act(login)}
                  >
                    Sign in with Onesa
                  </Button>
                  {!locked && (
                    <Button
                      colors={colors}
                      secondary
                      disabled={working}
                      onPress={() =>
                        act(() =>
                          Linking.openURL(
                            "https://portal.onesa.eu/account/security",
                          ),
                        )
                      }
                    >
                      Recover my Onesa account
                    </Button>
                  )}
                  {locked && (
                    <Button
                      colors={colors}
                      disabled={working}
                      onPress={() => act(refresh)}
                    >
                      Check connection
                    </Button>
                  )}
                  {!locked && (
                    <Button
                      colors={colors}
                      secondary
                      disabled={working}
                      onPress={() => setOpened(false)}
                    >
                      Open device-only planner
                    </Button>
                  )}
                </>
              )}
              {(account || locked) && (
                <Button
                  colors={colors}
                  secondary
                  disabled={working}
                  onPress={() => act(logout)}
                >
                  Sign out of Onesa
                </Button>
              )}
              {working && <Body colors={colors}>Contacting Onesa…</Body>}
              {!!notice && (
                <Text
                  accessibilityLiveRegion="polite"
                  style={[styles.body, { color: colors.text }]}
                >
                  {notice}
                </Text>
              )}
            </Panel>
            <Button
              colors={colors}
              secondary
              onPress={() =>
                act(() =>
                  Linking.openURL("https://portal.onesa.eu/account/delete"),
                )
              }
            >
              Request account deletion
            </Button>
            <Button
              colors={colors}
              secondary
              onPress={() =>
                act(() => Linking.openURL("https://onesa.eu/en/privacy"))
              }
            >
              Privacy notice
            </Button>
          </ScrollView>
        </SafeAreaView>
      )}
    </>
  );
}

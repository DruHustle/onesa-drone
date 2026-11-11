import React, { useEffect, useRef, useState } from "react";
import { Alert, Platform, Pressable, Share, Text, View } from "react-native";
import * as SecureStore from "expo-secure-store";
import { Body, Button, Input, Panel, styles } from "./field-ui.jsx";
import {
  BENCH_CHECKS, OUTCOME_LABELS, UnreadableBenchRecord, deleteReport, formatReport, loadReport, markCheck, saveReport, startReport,
} from "./bench-report.mjs";

export default function BenchPanel({ visible, colors }) {
  const [report, setReport] = useState(null);
  const [aircraft, setAircraft] = useState("");
  const [firmware, setFirmware] = useState("");
  const [vendorVersion, setVendorVersion] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [unreadable, setUnreadable] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  useEffect(() => {
    let active = true;
    setUnreadable(false);
    loadReport(SecureStore).then(saved => {
      if (active) { setReport(saved); setLoaded(true); setStatus(""); }
    }).catch(error => {
      if (!active) return;
      setUnreadable(error instanceof UnreadableBenchRecord);
      setStatus(error instanceof UnreadableBenchRecord ? error.message :
        "Could not read the encrypted bench record. Unlock the phone and retry.");
    });
    return () => { active = false; };
  }, [attempt]);

  async function persist(nextReport, removeUnreadable = false) {
    if (pending.current || !(loaded || (unreadable && removeUnreadable))) return;
    pending.current = true;
    setBusy(true);
    try {
      const next = nextReport();
      if (next) await saveReport(SecureStore, next);
      else await deleteReport(SecureStore);
      setReport(next);
      setUnreadable(false);
      setLoaded(true);
      setStatus(next ? "Saved on this device." : "Bench record deleted.");
      if (!next) { setAircraft(""); setFirmware(""); setVendorVersion(""); }
    } catch (error) {
      setStatus(error instanceof RangeError ? error.message :
        "Could not save this change. Check the fields and device storage, then retry.");
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  function clear() {
    Alert.alert("Delete this bench record?", report ? "This removes the saved results for " + report.aircraft +
      " from this phone." : "This permanently removes the unreadable record from this phone.", [
      { text: "Cancel", style: "cancel" },
      { text: "Delete", style: "destructive", onPress: () => persist(() => null, unreadable) },
    ]);
  }
  async function share() {
    try { await Share.share({ message: formatReport(report) }); }
    catch { setStatus("Could not open the share sheet. The record is saved on this device."); }
  }
  if (!visible) return null;
  return <Panel colors={colors}>
    <Text accessibilityRole="header" style={[styles.h3,{color:colors.text}]}>A77 ground bench record</Text>
    <Body colors={colors} muted small>Record what you see with the motors off. This worksheet stores one
      operator-entered record on this phone. It does not measure aircraft telemetry or assess flight readiness.</Body>
    {!!status && <Text accessibilityLiveRegion="polite" style={[styles.body,{color:colors.text}]}>{status}</Text>}
    {!loaded ? (status
      ? <>
          <Button colors={colors} secondary disabled={busy} onPress={() => { setStatus(""); setAttempt(n => n + 1); }}>Retry reading record</Button>
          {unreadable && <Button colors={colors} secondary disabled={busy} onPress={clear}>Delete unreadable record</Button>}
        </>
      : <Body colors={colors}>Reading saved record…</Body>) : !report ? <>
      <Input colors={colors} label="Aircraft asset label" value={aircraft} onChangeText={setAircraft}
        placeholder="E.g. Workshop A77-1" maxLength={40}/>
      <Input colors={colors} label="Aircraft firmware (if known)" value={firmware} onChangeText={setFirmware}
        placeholder="Unknown" maxLength={40}/>
      <Input colors={colors} label="CHUBORY FLY version (if known)" value={vendorVersion} onChangeText={setVendorVersion}
        placeholder="Unknown" maxLength={40}/>
      <Button colors={colors} disabled={busy || !aircraft.trim()} onPress={() =>
        persist(() => startReport({ aircraft, firmware, vendorVersion, platform: Platform.OS }))}>Start bench record</Button>
    </> : <>
      <Text style={[styles.label,{color:colors.text}]}>{report.aircraft}</Text>
      <Body colors={colors} muted small>{report.startedAt} · {report.platform} · Firmware {report.firmware || "unknown"}
        {" · CHUBORY FLY " + (report.vendorVersion || "unknown")}</Body>
      {BENCH_CHECKS.map(({ id, label }, index) => {
        const result = report.results[index];
        return <View key={id} style={[styles.item,{borderColor:colors.border}]}>
          <Text style={[styles.label,{color:colors.text}]}>{label}</Text>
          <Body colors={colors} muted small>{OUTCOME_LABELS[result.outcome]}{result.at && " · " + result.at}</Body>
          <View style={styles.wrap}>{Object.entries(OUTCOME_LABELS).map(([outcome, title]) =>
            <Pressable key={outcome} accessibilityRole="button" accessibilityLabel={label + ", " + title}
              accessibilityState={{selected: result.outcome === outcome, disabled: busy || result.outcome === outcome}}
              disabled={busy || result.outcome === outcome}
              style={[styles.pill,{borderColor:colors.border,backgroundColor:result.outcome === outcome ? colors.rail : colors.surface}]}
              onPress={() => persist(() => markCheck(report, id, outcome))}>
              <Text style={[styles.label,{color:colors.text}]}>{title}</Text>
            </Pressable>)}</View>
        </View>;
      })}
      <View style={styles.wrap}>
        <Button colors={colors} disabled={busy} onPress={share}>Share bench record</Button>
        <Button colors={colors} disabled={busy} secondary onPress={clear}>Delete record</Button>
      </View>
    </>}
  </Panel>;
}

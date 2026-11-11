import React, { useEffect, useRef, useState } from "react";
import { Alert, Pressable, Text, View } from "react-native";
import * as SecureStore from "expo-secure-store";
import { Body, Button, Input, Panel, styles } from "./field-ui.jsx";
import { NOTE_LIMIT, NOTE_SOURCES, makeObservation, loadObservations, saveObservation, deleteObservation } from "./observation-log.mjs";

export default function ObservationLog({active, colors}) {
  const [source, setSource] = useState("");
  const [note, setNote] = useState("");
  const [session, setSession] = useState([]);
  const [saved, setSaved] = useState(null);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);

  async function withStorage(operation) {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    try {
      await operation();
    } catch (error) {
      setStatus(error instanceof RangeError ? error.message :
        "Could not access the encrypted log. Unlock this device and try again.");
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  function refresh() {
    return withStorage(async () => {
      setSaved(await loadObservations(SecureStore));
      setStatus("");
    });
  }
  useEffect(() => {
    if (active) refresh();
  }, [active]);

  function add(persist) {
    let entry;
    try {
      entry = makeObservation(note, source, Date.now());
    } catch (error) {
      setStatus(error.message);
      return;
    }
    if (persist) {
      withStorage(async () => {
        setSaved(await saveObservation(SecureStore, entry));
        setNote("");
        setStatus("Saved in the encrypted log on this device.");
      });
    } else if (session.length >= NOTE_LIMIT) {
      setStatus("All 10 session slots are in use. Delete a session note to make room.");
    } else {
      setSession(previous => [entry, ...previous]);
      setNote("");
      setStatus("Added to the session. Closing the app clears session notes.");
    }
  }
  function confirmDelete(entry) {
    Alert.alert("Delete saved note?", "This removes the entry from this device.", [
      {text:"Cancel", style:"cancel"},
      {text:"Delete", style:"destructive", onPress:() => withStorage(async () => {
        setSaved(await deleteObservation(SecureStore, entry));
        setStatus("Saved note deleted.");
      })},
    ]);
  }
  if (!active) return null;
  function renderEntry(entry, remove, key) {
    return <View key={key} style={[styles.item,{borderColor:colors.border}]}>
      {entry.unreadable ? <Body colors={colors}>Unreadable saved entry</Body> : <>
        <Body colors={colors}>{entry.text}</Body>
        <Body colors={colors} muted small>{NOTE_SOURCES[entry.source]} · {new Date(entry.recordedAt).toISOString()}</Body>
      </>}
      <Button colors={colors} secondary disabled={busy} onPress={remove}>Delete note</Button>
    </View>;
  }
  return <Panel colors={colors}>
    <Text style={[styles.h3,{color:colors.text}]}>Human observations</Text>
    <Body colors={colors} muted small>Choose what you observed. Notes record the device time in UTC and stay on this device.</Body>
    <View style={styles.wrap}>{Object.entries(NOTE_SOURCES).map(([value, label]) =>
      <Pressable key={value} accessibilityRole="radio" accessibilityState={{checked:source===value,disabled:busy}}
        disabled={busy} onPress={()=>setSource(value)}
        style={[styles.pill,{borderColor:source===value?colors.brand:colors.border,
          backgroundColor:source===value?colors.rail:colors.surface}]}>
        <Text style={[styles.label,{color:colors.text}]}>{label}</Text>
      </Pressable>
    )}</View>
    <Input label="Inspection note" value={note} onChangeText={setNote} colors={colors}
      editable={!busy} placeholder="E.g. housing inspected on bench" maxLength={250}/>
    <View style={styles.wrap}>
      <Button colors={colors} secondary disabled={busy} onPress={()=>add(false)}>Add to session log</Button>
      <Button colors={colors} disabled={busy} onPress={()=>add(true)}>Save on device</Button>
    </View>
    {!!status && <Text accessibilityLiveRegion="polite" style={[styles.small,{color:colors.text}]}>{status}</Text>}
    {session.length > 0 && <>
      <Text style={[styles.label,{color:colors.text}]}>Session notes · {session.length} / {NOTE_LIMIT}</Text>
      {session.map((entry,i)=>renderEntry(entry,()=>setSession(rows=>rows.filter(row=>row!==entry)),i))}
    </>}
    <Text style={[styles.label,{color:colors.text}]}>Saved notes{saved && " · " + saved.length + " / " + NOTE_LIMIT}</Text>
    <Body colors={colors} muted small>Session notes clear when the app closes. Saved notes use encrypted storage until you delete them.</Body>
    {saved === null && <Body colors={colors} muted>{busy?"Reading encrypted notes…":"Saved notes unavailable."}</Body>}
    {saved?.map(entry=>renderEntry(entry,()=>confirmDelete(entry),entry.slot))}
    <Button colors={colors} secondary disabled={busy} onPress={refresh}>Refresh saved notes</Button>
  </Panel>;
}

import React, { useEffect, useMemo, useState } from "react";
import {
  Linking, Platform, Pressable, ScrollView, StatusBar,
  Text, View, useColorScheme,
} from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";
import Svg, { Circle, Line, Polyline, Rect, Text as SvgText } from "react-native-svg";
import * as SecureStore from "expo-secure-store";
import {
  A77, PURPOSES, DEMO_ROUTE, MAX_WAYPOINTS, aircraftLocation,
  waypoint, inspectRoute, makeDraft, simulationPosition, physicalDispatchStatus,
} from "./src/mission-core.mjs";
import { saveDraft, loadDrafts, deleteDraft } from "./src/mission-store.mjs";

import { Body, Button, Input, Panel, styles } from "./src/field-ui.jsx";
import BenchPanel from "./src/BenchPanel.jsx";
import AccountHome from "./src/AccountHome.jsx";
import {privateStore} from "./src/mobile-account.mjs";
import ObservationLog from "./src/ObservationLog.jsx";

const TABS = ["Plan", "Monitor", "Video", "Missions", "Aircraft"];
const palette = dark => dark ? {
  canvas:"#0B1823", surface:"#132638", text:"#F2FAFC", muted:"#B8CBD3",
  border:"#365164", brand:"#6CE4C4", brandText:"#062F29", accent:"#2A7890",
  rail:"#0D1E2A", danger:"#FFC6A3",
} : {
  canvas:"#F1F7F7", surface:"#FFFFFF", text:"#16313F", muted:"#4C626E",
  border:"#CCDDE1", brand:"#006D60", brandText:"#FFFFFF", accent:"#DDECEB",
  rail:"#E7F2F1", danger:"#A34A1A",
};
function RouteSketch({ points, marker, colors }) {
  const all = points.length ? points : DEMO_ROUTE;
  const lats = all.map(p=>p.lat), lons=all.map(p=>p.lon);
  const loLat = Math.min(...lats)-0.0005, hiLat=Math.max(...lats)+0.0005;
  const loLon = Math.min(...lons)-0.0005, hiLon=Math.max(...lons)+0.0005;
  const x = p => 22+316*(p.lon-loLon)/(hiLon-loLon);
  const y = p => 220-192*(p.lat-loLat)/(hiLat-loLat);
  const line = all.map(p=>x(p).toFixed(1)+","+y(p).toFixed(1)).join(" ");
  return <View accessible accessibilityLabel="Relative route sketch. Not a map or approved airspace plan."
      style={[styles.map,{backgroundColor:colors.rail}]}>
    <Svg viewBox="0 0 360 245" width="100%" height="100%">
      <Rect x="0" y="0" width="360" height="245" fill={colors.rail} />
      {[45,90,135,180,225,270,315].map(n=><Line key={"x"+n} x1={n} x2={n} y1="0" y2="245" stroke={colors.border}/>)}
      {[45,90,135,180,225].map(n=><Line key={"y"+n} y1={n} y2={n} x1="0" x2="360" stroke={colors.border}/>)}
      {all.length>1 && <Polyline points={line} stroke={colors.brand} strokeWidth="3" fill="none" strokeLinejoin="round" />}
      {all.map((p,i)=><React.Fragment key={i}>
        <Circle cx={x(p)} cy={y(p)} r="6" fill={colors.brand} stroke={colors.surface} strokeWidth="2"/>
        <SvgText x={x(p)+10} y={y(p)-9} fill={colors.text} fontSize="12">{i+1}</SvgText>
      </React.Fragment>)}
      {marker && <Circle cx={x(marker)} cy={y(marker)} r="9"
        stroke={colors.danger} strokeWidth="3" fill={colors.surface}/>}
      <SvgText x="12" y="238" fill={colors.muted} fontSize="11">RELATIVE GEOMETRY • NOT NAVIGATION DATA</SvgText>
    </Svg>
  </View>;
}

function Screen({account, colors, openAccount}) {
  const scope = account?.storage_scope;
  const store = useMemo(() => scope ? privateStore(SecureStore, scope) : SecureStore, [scope]);
  const [tab,setTab]=useState("Plan");
  const [purpose,setPurpose]=useState(PURPOSES[0].id);
  const [name,setName]=useState("Perimeter observation");
  const [lat,setLat]=useState(""),[lon,setLon]=useState("");
  const [points,setPoints]=useState([]);
  const [drafts,setDrafts]=useState([]);
  const [notice,setNotice]=useState("");
  const [busy,setBusy]=useState(false);
  const [simulating,setSimulating]=useState(false);
  const [progress,setProgress]=useState(0);
  const [checks,setChecks]=useState([]);
  useEffect(()=>{
    let mounted=true;
    loadDrafts(store).then(rows=>{if(mounted)setDrafts(rows);})
      .catch(()=>{if(mounted)setNotice("Encrypted storage unavailable. Drafts are not saved.");});
    return ()=>{mounted=false;};
  },[store]);
  useEffect(()=>{
    if(!simulating)return;
    const timer=setInterval(()=>setProgress(p=>Math.min(1,p+0.018)),700);
    return ()=>clearInterval(timer);
  },[simulating]);
  useEffect(()=>{if(progress>=1 && simulating)setSimulating(false);},[progress,simulating]);
  const review=useMemo(()=>{
    try{return inspectRoute(points);}catch{return null;}
  },[points]);
  const marker=useMemo(()=>{
    if(!review)return null;
    try{return simulationPosition(points,progress);}catch{return null;}
  },[points,progress,review]);
  function addPoint(){
    try{
      if(points.length>=MAX_WAYPOINTS)throw new Error("Route limit reached");
      const point=waypoint(lat.trim(),lon.trim());
      setPoints(old=>[...old,point]);setLat("");setLon("");setProgress(0);setSimulating(false);setNotice("Waypoint added to offline route draft.");
    }catch(error){setNotice(error.message||"Invalid point");}
  }
  async function save(){
    if(busy)return;
    setBusy(true);
    try{
      const draft=makeDraft({
        title:name,purpose,points,id:"draft_"+Date.now().toString(36)+"_"+Math.floor(Math.random()*1e7).toString(36),
        now:Date.now(),
      });
      await saveDraft(store,draft);
      setDrafts(await loadDrafts(store));
      setNotice("Encrypted mission draft saved on this device. Nothing was dispatched.");
      setTab("Missions");
    }catch(error){setNotice(error.message||"Draft could not be saved");}
    finally{setBusy(false);}
  }
  async function remove(id){
    if(busy)return;
    setBusy(true);
    try{
      await deleteDraft(store,id);
      setDrafts(await loadDrafts(store));
      setNotice("Device-local draft deleted.");
    }catch{setNotice("Could not delete the encrypted draft.");}
    finally{setBusy(false);}
  }
  function load(draft){
    setName(draft.title);setPurpose(draft.purpose);setPoints(draft.waypoints);
    setProgress(0);setSimulating(false);setTab("Plan");
    setNotice("Draft loaded. Physical aircraft remains disconnected.");
  }
  function demo(){
    setName("Example security perimeter");setPurpose("facility-security");
    setPoints(DEMO_ROUTE.map(p=>({...p})));setProgress(0);setSimulating(false);
    setNotice("Illustrative points loaded, not your farm or actual aircraft GPS.");
  }
  async function vendorApp(){
    const url=Platform.OS==="ios"
      ?"https://apps.apple.com/app/id6467178101"
      :"https://play.google.com/store/apps/details?id=com.h8.chubory";
    try{await Linking.openURL(url);}catch{setNotice("Open CHUBORY FLY in your device's app store.");}
  }
  const title={Plan:"Mission planner",Monitor:"Aircraft position",Video:"Video & evidence",Missions:"Encrypted drafts",Aircraft:"Aircraft & safety"}[tab];
  const hardware=aircraftLocation(),dispatch=physicalDispatchStatus();
  const planningChecks=[
    "A qualified remote pilot and visual line of sight are available",
    "Current weather, obstacles, terrain and airspace were independently checked",
    "Privacy, people, livestock and wildlife risks were assessed",
    "Battery, link, failsafes and return-to-home were verified on the actual aircraft",
  ];
  return <SafeAreaView style={[styles.root,{backgroundColor:colors.canvas}]} edges={["top","bottom"]}>
    <StatusBar barStyle={colors.canvas==="#0B1823"?"light-content":"dark-content"}/>
    <View style={[styles.header,{borderBottomColor:colors.border,borderBottomWidth:1}]}>
      <Text style={[styles.eyebrow,{color:colors.brand}]}>ONESA / FIELD OPERATIONS</Text>
      <Text style={[styles.brand,{color:colors.text}]}>Drone Mission Control</Text>
      {openAccount
        ? <Button secondary colors={colors} onPress={openAccount}>{account ? account.email : "Onesa account"}</Button>
        : <Body colors={colors} small>Bench edition · Device-only records</Body>}
      <Body colors={colors} muted small>CHUBORY A77 prototype  ·  Offline planner  ·  No live aircraft connection</Body>
    </View>
    <ScrollView style={styles.scroll} contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled" keyboardDismissMode="on-drag">
      <View style={{paddingTop:15,gap:5}}>
        <Text accessibilityRole="header" style={[styles.title,{color:colors.text}]}>{title}</Text>
        <Body colors={colors} muted small>SIMULATION ONLY · Physical launch and remote commands disabled</Body>
      </View>
      {!!notice && <View style={[styles.notice,{borderColor:colors.brand,backgroundColor:colors.surface}]}>
        <Text accessibilityLiveRegion="polite" style={[styles.small,{color:colors.text}]}>{notice}</Text>
      </View>}

      {tab==="Plan" && <>
        <Panel colors={colors}>
          <Text style={[styles.h3,{color:colors.text}]}>Choose your operation</Text>
          <View style={styles.wrap}>{PURPOSES.map(p=><Pressable key={p.id} accessibilityRole="button"
            accessibilityState={{selected:p.id===purpose}} onPress={()=>setPurpose(p.id)}
            style={[styles.pill,{borderColor:p.id===purpose?colors.brand:colors.border,
              backgroundColor:p.id===purpose?colors.rail:colors.surface}]}>
              <Text style={[styles.label,{color:colors.text}]}>{p.label}</Text>
            </Pressable>)}</View>
          <Body colors={colors} muted small>{PURPOSES.find(p=>p.id===purpose)?.detail}</Body>
          <Input label="Mission name" value={name} onChangeText={setName} colors={colors} placeholder="Inspection name"/>
        </Panel>
        <Panel colors={colors}>
          <Text style={[styles.h3,{color:colors.text}]}>Waypoints</Text>
          <Body colors={colors} muted>Enter coordinates from a verified map. The drawing is a relative route sketch, not a flight-approved map.</Body>
          <View style={styles.grid}>
            <Input label="Latitude" value={lat} onChangeText={setLat} colors={colors}
              keyboardType="numbers-and-punctuation" placeholder="-17.800000" maxLength={16}/>
            <Input label="Longitude" value={lon} onChangeText={setLon} colors={colors}
              keyboardType="numbers-and-punctuation" placeholder="31.000000" maxLength={16}/>
          </View>
          <View style={styles.wrap}>
            <Button colors={colors} onPress={addPoint} disabled={points.length>=MAX_WAYPOINTS}>+ Add waypoint</Button>
            <Button colors={colors} secondary onPress={demo}>Load example</Button>
            <Button colors={colors} secondary onPress={()=>{setPoints([]);setProgress(0);setSimulating(false);}}>Clear</Button>
          </View>
          <RouteSketch colors={colors} points={points} />
          <Body colors={colors} muted small>{points.length?points.length+" of "+MAX_WAYPOINTS+" points":"Example geometry shown until you enter a route."}</Body>
          {points.map((p,i)=><View key={i} style={[styles.item,{borderColor:colors.border}]}>
            <View style={styles.row}>
              <View style={styles.grow}>
                <Text style={[styles.label,{color:colors.text}]}>Point {i+1}</Text>
                <Body colors={colors} small>{p.lat.toFixed(6)}, {p.lon.toFixed(6)}</Body>
              </View>
              <Button colors={colors} secondary onPress={()=>{
                setPoints(old=>old.filter((_,idx)=>idx!==i));setSimulating(false);setProgress(0);
              }}>Remove</Button>
            </View>
          </View>)}
        </Panel>
        <Panel colors={colors}>
          <Text style={[styles.h3,{color:colors.text}]}>Review before saving</Text>
          <Body colors={colors}>{review?review.distance_m.toLocaleString()+" m estimated ground route":"Add at least two distinct waypoints."}</Body>
          <Body colors={colors} muted small>No terrain clearance, flight endurance, GPS, airspace or payload feasibility has been confirmed.</Body>
          <View style={styles.wrap}>
            <Button colors={colors} disabled={!review||busy} onPress={save}>{busy?"Saving…":"Save encrypted draft"}</Button>
            <Button colors={colors} secondary disabled={!review} onPress={()=>{setTab("Monitor");setSimulating(true);setProgress(0);}}>Preview simulation</Button>
          </View>
        </Panel>
      </>}

      {tab==="Monitor" && <>
        <Panel colors={colors}>
          <Text style={[styles.h3,{color:colors.text}]}>Actual CHUBORY A77 location</Text>
          <Text style={[styles.title,{color:colors.danger}]}>Not available</Text>
          <Body colors={colors}>No verified GPS or remote telemetry is connected. A phone location must never be presented as an aircraft position.</Body>
          <Body colors={colors} muted small>Source: {hardware.source} · Last received: none · Battery: unknown</Body>
        </Panel>
        <Panel colors={colors}>
          <View style={styles.row}>
            <Text style={[styles.h3,styles.grow,{color:colors.text}]}>Synthetic route replay</Text>
            <Body colors={colors} small muted>{Math.round(progress*100)}%</Body>
          </View>
          <RouteSketch points={points} marker={marker} colors={colors}/>
          <Body colors={colors} muted small>{marker?"SIMULATED POSITION: "+marker.lat.toFixed(6)+", "+marker.lon.toFixed(6):"Set at least two waypoints on the Plan tab to start."}</Body>
          <View style={styles.wrap}>
            <Button colors={colors} disabled={!review} onPress={()=>{if(progress>=1)setProgress(0);setSimulating(!simulating);}}>
              {simulating?"Pause replay":"Play replay"}
            </Button>
            <Button colors={colors} secondary onPress={()=>{setProgress(0);setSimulating(false);}}>Reset</Button>
          </View>
          <Body colors={colors} muted small>Demo marker is calculated locally. It is never transmitted to, or read from, the aircraft.</Body>
        </Panel>
      </>}
      <ObservationLog store={store} active={tab==="Monitor"} colors={colors}/>

      {tab==="Video" && <>
        <Panel colors={colors}>
          <Text style={[styles.h3,{color:colors.text}]}>Inspection camera</Text>
          <View style={[styles.media,{backgroundColor:colors.rail}]}>
            <Text style={[styles.title,{color:colors.text}]}>No live feed</Text>
            <Body colors={colors} muted style={{textAlign:"center"}}>A77 video is available through its own Wi-Fi companion app. An authenticated stream bridge is not verified.</Body>
          </View>
          <Button colors={colors} onPress={vendorApp}>View CHUBORY FLY in the store</Button>
          <Body colors={colors} muted small>Use the manufacturer's control app while flying. This screen does not mirror, relay, record or stream camera footage.</Body>
        </Panel>
        <Panel colors={colors}>
          <Text style={[styles.h3,{color:colors.text}]}>Future video integration gates</Text>
          <Body colors={colors}>A supported camera protocol, device pairing, encrypted transport, explicit viewer permissions, retention controls and real-device tests are required before Onesa can show a remote feed.</Body>
          <Body colors={colors} muted small>Do not use recorded demo footage as evidence of a live security or wildlife inspection.</Body>
        </Panel>
      </>}

      {tab==="Missions" && <>
        <Panel colors={colors}>
          <Text style={[styles.h3,{color:colors.text}]}>Saved on this device</Text>
          <Body colors={colors} muted small>Drafts use iOS Keychain or Android Keystore. They are not synced to Onesa servers or sent to your aircraft.</Body>
          {!drafts.length && <Body colors={colors}>No saved routes yet. Create one under Plan.</Body>}
          {drafts.map(d=><View key={d.id} style={[styles.item,{borderColor:colors.border}]}>
            <Text style={[styles.h3,{color:colors.text}]}>{d.title}</Text>
            <Body colors={colors} muted small>{PURPOSES.find(p=>p.id===d.purpose)?.label} · {d.waypoints.length} points · {d.distance_m} m · DRAFT</Body>
            <View style={styles.wrap}>
              <Button colors={colors} secondary onPress={()=>load(d)}>Open route</Button>
              <Button colors={colors} secondary disabled={busy} onPress={()=>remove(d.id)}>Delete</Button>
            </View>
          </View>)}
        </Panel>
      </>}

      {tab==="Aircraft" && <>
        <Panel colors={colors}>
          <Text style={[styles.h3,{color:colors.text}]}>{A77.manufacturer} · {A77.model}</Text>
          {[
            ["Onesa aircraft connection", "Disconnected"],
            ["Position / GPS", "Unverified"],
            ["Real-time cloud video", "No supported relay"],
            ["Waypoint dispatch", "Disabled"],
            ["Delivery payload", "Unqualified"],
            ["Automatic security patrol", "Disabled"],
          ].map(([a,b])=><View key={a} style={[styles.row,{justifyContent:"space-between"}]}>
            <Body colors={colors} muted small>{a}</Body>
            <Body colors={colors} small style={{textAlign:"right",maxWidth:"60%"}}>{b}</Body>
          </View>)}
          <Button colors={colors} secondary onPress={vendorApp}>View CHUBORY FLY in the store</Button>
          <Body colors={colors} muted small>{dispatch.reason}</Body>
        </Panel>
        <Panel colors={colors}>
          <Text style={[styles.h3,{color:colors.text}]}>Preflight planning checklist</Text>
          <Body colors={colors} muted small>For human review only. Checking these does not authorize launch or satisfy aviation requirements.</Body>
          {planningChecks.map((item,i)=><Pressable key={i} accessibilityRole="checkbox"
            accessibilityState={{checked:checks.includes(i)}} onPress={()=>
              setChecks(old=>old.includes(i)?old.filter(x=>x!==i):[...old,i])
            } style={[styles.row,{minHeight:48}]}>
              <Text style={[styles.h3,{color:colors.brand}]}>{checks.includes(i)?"☑":"☐"}</Text>
              <View style={styles.grow}><Body colors={colors}>{item}</Body></View>
            </Pressable>)}
          <Body colors={colors} muted small>{checks.length} / {planningChecks.length} reviewed · Physical dispatch remains locked.</Body>
        </Panel>
      </>}
      <BenchPanel store={store} visible={tab==="Aircraft"} colors={colors}/>
    </ScrollView>
    <View style={[styles.tabRail,{borderColor:colors.border,backgroundColor:colors.surface}]}>
      {TABS.map(next=><Pressable key={next} testID={"planner-tab-"+next} accessibilityRole="tab"
        accessibilityState={{selected:next===tab}} onPress={()=>setTab(next)} style={styles.tab}>
        <View style={[styles.marker,{backgroundColor:next===tab?colors.brand:"transparent"}]}/>
        <Text style={[styles.tabText,{color:next===tab?colors.brand:colors.muted}]}>{next}</Text>
      </Pressable>)}
    </View>
  </SafeAreaView>;
}
export function OfflineBenchApp() {
  const colors = palette(useColorScheme() === "dark");
  return <SafeAreaProvider><Screen colors={colors}/></SafeAreaProvider>;
}

export default function App() {
  const colors = palette(useColorScheme() === "dark");
  return <SafeAreaProvider><AccountHome colors={colors}>
    {(account, openAccount) => <Screen key={account?.storage_scope || "device"} colors={colors}
      account={account} openAccount={openAccount}/>}
  </AccountHome></SafeAreaProvider>;
}

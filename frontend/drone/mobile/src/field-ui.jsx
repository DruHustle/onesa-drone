import React from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

export const styles = StyleSheet.create({
  root:{ flex:1 }, scroll:{ flex:1 }, content:{ paddingHorizontal:16, paddingBottom:30, gap:14, maxWidth:720, alignSelf:"center", width:"100%" },
  header:{ paddingHorizontal:18, paddingTop:10, paddingBottom:14, gap:5 },
  eyebrow:{ fontSize:11, fontWeight:"800", letterSpacing:1.6, textTransform:"uppercase" },
  brand:{ fontSize:25, fontWeight:"800" }, title:{ fontSize:21, fontWeight:"800" },
  h3:{ fontSize:16, fontWeight:"700" }, body:{ fontSize:14, lineHeight:21 },
  small:{ fontSize:12, lineHeight:18 }, label:{ fontSize:13, fontWeight:"700" },
  card:{ borderWidth:1, borderRadius:15, padding:16, gap:12 },
  row:{ flexDirection:"row", alignItems:"center", gap:10 },
  wrap:{ flexDirection:"row", gap:8, flexWrap:"wrap" }, grow:{ flex:1 },
  button:{ paddingHorizontal:14, minHeight:46, borderRadius:11, justifyContent:"center", alignItems:"center", borderWidth:1 },
  buttonText:{ fontWeight:"800", fontSize:13, textAlign:"center" },
  pill:{ minHeight:44, paddingHorizontal:13, paddingVertical:10, borderWidth:1, borderRadius:12, justifyContent:"center" },
  input:{ minHeight:48, borderWidth:1, borderRadius:10, paddingHorizontal:12, fontSize:15 },
  grid:{ flexDirection:"row", gap:9 }, half:{ flex:1, minWidth:0 },
  item:{ borderTopWidth:1, paddingVertical:11, gap:5 },
  tabRail:{ borderTopWidth:1, flexDirection:"row", paddingHorizontal:5 },
  tab:{ flex:1, minHeight:60, justifyContent:"center", alignItems:"center", gap:3 },
  tabText:{ fontSize:11, fontWeight:"700", textAlign:"center" },
  marker:{ height:7, width:7, borderRadius:4 },
  map:{ width:"100%", height:250, borderRadius:12, overflow:"hidden" },
  media:{ height:215, borderRadius:13, justifyContent:"center", alignItems:"center", padding:20, gap:12 },
  divider:{ height:1 }, notice:{ borderWidth:1, borderRadius:10, padding:12 },
});
export function Panel({ children, colors }) {
  return <View style={[styles.card,{backgroundColor:colors.surface,borderColor:colors.border}]}>{children}</View>;
}
export function Body({ children, colors, muted=false, small=false, style, testID }) {
  return <Text testID={testID} style={[small?styles.small:styles.body,{color:muted?colors.muted:colors.text},style]}>{children}</Text>;
}
export function Button({ children, onPress, colors, secondary=false, disabled=false, style }) {
  return <Pressable accessibilityRole="button" accessibilityState={{disabled}} onPress={onPress}
    disabled={disabled} style={({pressed})=>[styles.button,{borderColor:colors.brand,
      backgroundColor:secondary?colors.surface:colors.brand,opacity:disabled?0.45:pressed?0.75:1},style]}>
    <Text style={[styles.buttonText,{color:secondary?colors.brand:colors.brandText}]}>{children}</Text>
  </Pressable>;
}
export function Input({label,value,onChangeText,colors,placeholder,keyboardType="default",maxLength=80,editable=true}) {
  return <View style={{gap:6,flex:1}}>
    <Text style={[styles.label,{color:colors.text}]}>{label}</Text>
    <TextInput accessibilityLabel={label} value={value} onChangeText={onChangeText}
      placeholder={placeholder} placeholderTextColor={colors.muted} keyboardType={keyboardType}
      autoCorrect={false} editable={editable} maxLength={maxLength} selectionColor={colors.brand}
      style={[styles.input,{backgroundColor:colors.surface,borderColor:colors.border,color:colors.text}]} />
  </View>;
}

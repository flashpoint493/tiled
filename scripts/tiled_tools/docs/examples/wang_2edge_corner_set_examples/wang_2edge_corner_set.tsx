<?xml version="1.0" encoding="UTF-8"?>
<tileset version="1.10" tiledversion="1.11" name="wang_2edge_corner_sand_water" tilewidth="64" tileheight="64" tilecount="32" columns="8">
 <image source="wang_2edge_corner_set.png" width="512" height="256"/>
 <tile id="0">
  <properties>
   <property name="name" value="edge_00"/>
  </properties>
 </tile>
 <tile id="1">
  <properties>
   <property name="name" value="edge_01"/>
  </properties>
 </tile>
 <tile id="2">
  <properties>
   <property name="name" value="edge_02"/>
  </properties>
 </tile>
 <tile id="3">
  <properties>
   <property name="name" value="edge_03"/>
  </properties>
 </tile>
 <tile id="4">
  <properties>
   <property name="name" value="edge_04"/>
  </properties>
 </tile>
 <tile id="5">
  <properties>
   <property name="name" value="edge_05"/>
  </properties>
 </tile>
 <tile id="6">
  <properties>
   <property name="name" value="edge_06"/>
  </properties>
 </tile>
 <tile id="7">
  <properties>
   <property name="name" value="edge_07"/>
  </properties>
 </tile>
 <tile id="8">
  <properties>
   <property name="name" value="edge_08"/>
  </properties>
 </tile>
 <tile id="9">
  <properties>
   <property name="name" value="edge_09"/>
  </properties>
 </tile>
 <tile id="10">
  <properties>
   <property name="name" value="edge_10"/>
  </properties>
 </tile>
 <tile id="11">
  <properties>
   <property name="name" value="edge_11"/>
  </properties>
 </tile>
 <tile id="12">
  <properties>
   <property name="name" value="edge_12"/>
  </properties>
 </tile>
 <tile id="13">
  <properties>
   <property name="name" value="edge_13"/>
  </properties>
 </tile>
 <tile id="14">
  <properties>
   <property name="name" value="edge_14"/>
  </properties>
 </tile>
 <tile id="15">
  <properties>
   <property name="name" value="edge_15"/>
  </properties>
 </tile>
 <tile id="16">
  <properties>
   <property name="name" value="corner_00"/>
  </properties>
 </tile>
 <tile id="17">
  <properties>
   <property name="name" value="corner_01"/>
  </properties>
 </tile>
 <tile id="18">
  <properties>
   <property name="name" value="corner_02"/>
  </properties>
 </tile>
 <tile id="19">
  <properties>
   <property name="name" value="corner_03"/>
  </properties>
 </tile>
 <tile id="20">
  <properties>
   <property name="name" value="corner_04"/>
  </properties>
 </tile>
 <tile id="21">
  <properties>
   <property name="name" value="corner_05"/>
  </properties>
 </tile>
 <tile id="22">
  <properties>
   <property name="name" value="corner_06"/>
  </properties>
 </tile>
 <tile id="23">
  <properties>
   <property name="name" value="corner_07"/>
  </properties>
 </tile>
 <tile id="24">
  <properties>
   <property name="name" value="corner_08"/>
  </properties>
 </tile>
 <tile id="25">
  <properties>
   <property name="name" value="corner_09"/>
  </properties>
 </tile>
 <tile id="26">
  <properties>
   <property name="name" value="corner_10"/>
  </properties>
 </tile>
 <tile id="27">
  <properties>
   <property name="name" value="corner_11"/>
  </properties>
 </tile>
 <tile id="28">
  <properties>
   <property name="name" value="corner_12"/>
  </properties>
 </tile>
 <tile id="29">
  <properties>
   <property name="name" value="corner_13"/>
  </properties>
 </tile>
 <tile id="30">
  <properties>
   <property name="name" value="corner_14"/>
  </properties>
 </tile>
 <tile id="31">
  <properties>
   <property name="name" value="corner_15"/>
  </properties>
 </tile>
 <wangsets>
  <wangset name="edge_set" type="edge" tile="15">
   <wangcolor name="background" color="#378dc2" tile="0" probability="1"/>
   <wangcolor name="foreground" color="#c4a000" tile="15" probability="1"/>
   <wangtile tileid="0" wangid="1,0,1,0,1,0,1,0"/>
   <wangtile tileid="1" wangid="2,0,1,0,1,0,1,0"/>
   <wangtile tileid="2" wangid="1,0,2,0,1,0,1,0"/>
   <wangtile tileid="3" wangid="2,0,2,0,1,0,1,0"/>
   <wangtile tileid="4" wangid="1,0,1,0,2,0,1,0"/>
   <wangtile tileid="5" wangid="2,0,1,0,2,0,1,0"/>
   <wangtile tileid="6" wangid="1,0,2,0,2,0,1,0"/>
   <wangtile tileid="7" wangid="2,0,2,0,2,0,1,0"/>
   <wangtile tileid="8" wangid="1,0,1,0,1,0,2,0"/>
   <wangtile tileid="9" wangid="2,0,1,0,1,0,2,0"/>
   <wangtile tileid="10" wangid="1,0,2,0,1,0,2,0"/>
   <wangtile tileid="11" wangid="2,0,2,0,1,0,2,0"/>
   <wangtile tileid="12" wangid="1,0,1,0,2,0,2,0"/>
   <wangtile tileid="13" wangid="2,0,1,0,2,0,2,0"/>
   <wangtile tileid="14" wangid="1,0,2,0,2,0,2,0"/>
   <wangtile tileid="15" wangid="2,0,2,0,2,0,2,0"/>
  </wangset>
  <wangset name="corner_set" type="corner" tile="31">
   <wangcolor name="background" color="#378dc2" tile="16" probability="1"/>
   <wangcolor name="foreground" color="#c4a000" tile="31" probability="1"/>
   <wangtile tileid="16" wangid="0,1,0,1,0,1,0,1"/>
   <wangtile tileid="17" wangid="0,1,0,1,0,1,0,2"/>
   <wangtile tileid="18" wangid="0,2,0,1,0,1,0,1"/>
   <wangtile tileid="19" wangid="0,2,0,1,0,1,0,2"/>
   <wangtile tileid="20" wangid="0,1,0,2,0,1,0,1"/>
   <wangtile tileid="21" wangid="0,1,0,2,0,1,0,2"/>
   <wangtile tileid="22" wangid="0,2,0,2,0,1,0,1"/>
   <wangtile tileid="23" wangid="0,2,0,2,0,1,0,2"/>
   <wangtile tileid="24" wangid="0,1,0,1,0,2,0,1"/>
   <wangtile tileid="25" wangid="0,1,0,1,0,2,0,2"/>
   <wangtile tileid="26" wangid="0,2,0,1,0,2,0,1"/>
   <wangtile tileid="27" wangid="0,2,0,1,0,2,0,2"/>
   <wangtile tileid="28" wangid="0,1,0,2,0,2,0,1"/>
   <wangtile tileid="29" wangid="0,1,0,2,0,2,0,2"/>
   <wangtile tileid="30" wangid="0,2,0,2,0,2,0,1"/>
   <wangtile tileid="31" wangid="0,2,0,2,0,2,0,2"/>
  </wangset>
 </wangsets>
</tileset>

import streamlit as st
import folium
from streamlit_folium import st_folium
from folium import plugins
import math
import json
import os
import random
import time
import threading
import queue
from datetime import datetime
import pandas as pd
import plotly.graph_objects as go

# ==================== 页面配置 ====================
st.set_page_config(page_title="无人机智能监控系统", page_icon="🛰️", layout="wide")

# ==================== 南京科技职业学院坐标 ====================
CAMPUS = [32.234097, 118.749413]

# ==================== 初始化 Session State ====================
if 'obstacles' not in st.session_state:
    st.session_state.obstacles = []
if 'point_a' not in st.session_state:
    st.session_state.point_a = [32.2323, 118.749]
if 'point_b' not in st.session_state:
    st.session_state.point_b = [32.2344, 118.749]
if 'flight_alt' not in st.session_state:
    st.session_state.flight_alt = 20
if 'route_plans' not in st.session_state:
    st.session_state.route_plans = []
if 'selected_plan' not in st.session_state:
    st.session_state.selected_plan = None
if 'confirmed_plan' not in st.session_state:
    st.session_state.confirmed_plan = None
if 'temp_obs' not in st.session_state:
    st.session_state.temp_obs = None
if 'temp_h' not in st.session_state:
    st.session_state.temp_h = [0, 30]
if 'temp_name' not in st.session_state:
    st.session_state.temp_name = "教学楼"
if 'heartbeat_running' not in st.session_state:
    st.session_state.heartbeat_running = False
if 'heartbeat_data' not in st.session_state:
    st.session_state.heartbeat_data = []

# ==================== 心跳模拟器 ====================
class HeartbeatSimulator:
    def __init__(self):
        self.running = False
        self.last_time = None
        self.offline = False
        self.history = []
    
    def start(self):
        self.running = True
        self.offline = False
        self.history = []
        self.last_time = time.time()
    
    def stop(self):
        self.running = False
    
    def update(self):
        if not self.running:
            return None
        
        current = time.time()
        elapsed = current - self.last_time
        
        if elapsed >= 1:
            self.last_time = current
            heartbeat = {
                'id': len(self.history) + 1,
                'time': datetime.now().strftime("%H:%M:%S"),
                'status': 'alive',
                'delay': round(random.uniform(5, 50), 2)
            }
            self.history.append(heartbeat)
            if len(self.history) > 50:
                self.history.pop(0)
            return heartbeat
        
        if elapsed > 3 and not self.offline:
            self.offline = True
            timeout = {
                'id': len(self.history) + 1,
                'time': datetime.now().strftime("%H:%M:%S"),
                'status': 'timeout',
                'delay': 0
            }
            self.history.append(timeout)
            return timeout
        elif elapsed <= 3 and self.offline:
            self.offline = False
        
        return None
    
    def get_stats(self):
        if not self.history:
            return {'total': 0, 'timeout': 0, 'rate': 100}
        total = len(self.history)
        timeout = sum(1 for h in self.history if h['status'] == 'timeout')
        return {'total': total, 'timeout': timeout, 'rate': round((total-timeout)/total*100, 1)}
    
    def get_history(self):
        return self.history.copy()

if 'heartbeat_sim' not in st.session_state:
    st.session_state.heartbeat_sim = HeartbeatSimulator()

# ==================== 工具函数 ====================
def calc_distance(p1, p2):
    lat1, lon1 = math.radians(p1[0]), math.radians(p1[1])
    lat2, lon2 = math.radians(p2[0]), math.radians(p2[1])
    R = 6371000
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def point_in_polygon(point, poly):
    x, y = point[1], point[0]
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i][1], poly[i][0]
        x2, y2 = poly[(i+1)%n][1], poly[(i+1)%n][0]
        if ((y1 > y) != (y2 > y)) and (x < (x2-x1)*(y-y1)/(y2-y1)+x1):
            inside = not inside
    return inside

class Obstacle:
    def __init__(self, points, min_h, max_h, name):
        self.points = points
        self.min_h = min_h
        self.max_h = max_h
        self.name = name
        lats = [p[0] for p in points]
        lons = [p[1] for p in points]
        self.cx = (min(lats)+max(lats))/2
        self.cy = (min(lons)+max(lons))/2
    
    def contains(self, point):
        return point_in_polygon(point, self.points)
    
    def get_left_bypass(self, start, end):
        dx = end[1] - start[1]
        dy = end[0] - start[0]
        L = math.sqrt(dx*dx+dy*dy)
        if L > 0:
            dx /= L
            dy /= L
        px = -dy
        py = dx
        off = 0.003
        return [self.cx + py*off, self.cy + px*off]
    
    def get_right_bypass(self, start, end):
        dx = end[1] - start[1]
        dy = end[0] - start[0]
        L = math.sqrt(dx*dx+dy*dy)
        if L > 0:
            dx /= L
            dy /= L
        px = -dy
        py = dx
        off = 0.003
        return [self.cx - py*off, self.cy - px*off]

# ==================== 标题 ====================
st.title("🛰️ 无人机智能监控系统")
st.markdown("**南京科技职业学院** | 3D障碍物 | 多航线选择 | 心跳监控")
st.markdown("---")

# ==================== 标签页 ====================
tab1, tab2 = st.tabs(["🗺️ 航线规划", "💓 心跳监控"])

# ==================== Tab 1: 航线规划 ====================
with tab1:
    col_left, col_right = st.columns([1.5, 1])
    
    with col_left:
        st.subheader("🗺️ 卫星地图")
        
        m = folium.Map(location=CAMPUS, zoom_start=17, control_scale=True)
        folium.TileLayer(
            'https://webst0{s}.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}',
            attr='高德卫星', subdomains=['1','2','3','4']
        ).add_to(m)
        
        folium.Marker(CAMPUS, popup="🏫 南京科技职业学院", icon=folium.Icon(color='red')).add_to(m)
        
        alt = st.session_state.flight_alt
        for obs in st.session_state.obstacles:
            if alt < obs.min_h:
                color = 'red'
            elif alt > obs.max_h:
                color = 'green'
            else:
                color = 'orange'
            folium.Polygon(
                obs.points, color=color, weight=2, fill=True,
                fill_color=color, fill_opacity=0.3,
                popup=f"{obs.name}\n{obs.min_h}-{obs.max_h}m"
            ).add_to(m)
        
        folium.Marker(st.session_state.point_a, popup="🚁 起点A", icon=folium.Icon(color='green')).add_to(m)
        folium.Marker(st.session_state.point_b, popup="🎯 终点B", icon=folium.Icon(color='red')).add_to(m)
        
        if st.session_state.selected_plan:
            p = st.session_state.selected_plan
            folium.PolyLine(p['points'], color=p['color'], weight=4).add_to(m)
            if len(p['points']) > 2:
                folium.Marker(p['points'][1], popup="绕行点", icon=folium.Icon(color='purple')).add_to(m)
        
        plugins.Draw(draw_options={'polygon': {'allowIntersection': False}}).add_to(m)
        plugins.MeasureControl().add_to(m)
        
        output = st_folium(m, width=650, height=450, key="map")
        
        if output and output.get('last_active_drawing'):
            d = output['last_active_drawing']
            if d and d['geometry']['type'] == 'Polygon':
                pts = [[c[1], c[0]] for c in d['geometry']['coordinates'][0]]
                if len(pts) >= 3:
                    st.session_state.temp_obs = pts
                    st.success(f"✅ 已绘制 {len(pts)} 个点")
    
    with col_right:
        # 新建障碍物
        if st.session_state.temp_obs:
            st.markdown("### 🆕 新建障碍物")
            name = st.text_input("名称", value=st.session_state.temp_name)
            st.session_state.temp_name = name if name else "障碍物"
            
            col1, col2 = st.columns(2)
            with col1:
                # 修复：确保默认值在有效范围内
                default_min = st.session_state.temp_h[0]
                if default_min < 0 or default_min > 200:
                    default_min = 0
                min_h = st.number_input("最低高度(m)", value=default_min, min_value=0, max_value=200, step=5)
            with col2:
                default_max = st.session_state.temp_h[1]
                if default_max < min_h + 1 or default_max > 300:
                    default_max = min_h + 10
                max_h = st.number_input("最高高度(m)", value=default_max, min_value=min_h + 1, max_value=300, step=5)
            
            st.session_state.temp_h = [min_h, max_h]
            
            # 进度条
            progress_val = max(0, min(1.0, max_h / 300))
            st.progress(progress_val)
            st.caption(f"📊 障碍物高度: {min_h}m - {max_h}m")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ 保存", type="primary", use_container_width=True):
                    new_obs = Obstacle(st.session_state.temp_obs, min_h, max_h, st.session_state.temp_name)
                    st.session_state.obstacles.append(new_obs)
                    st.session_state.temp_obs = None
                    st.session_state.route_plans = []
                    st.session_state.selected_plan = None
                    st.rerun()
            with col2:
                if st.button("🗑️ 取消", use_container_width=True):
                    st.session_state.temp_obs = None
                    st.rerun()
            st.markdown("---")
        
        # 起点
        st.markdown("### 🚁 起点 A")
        col1, col2 = st.columns(2)
        with col1:
            la = st.number_input("纬度", value=st.session_state.point_a[0], format="%.6f")
        with col2:
            lo = st.number_input("经度", value=st.session_state.point_a[1], format="%.6f")
        if st.button("📍 设置A点", use_container_width=True):
            st.session_state.point_a = [la, lo]
            st.session_state.route_plans = []
            st.rerun()
        
        # 终点
        st.markdown("### 🎯 终点 B")
        col1, col2 = st.columns(2)
        with col1:
            lb = st.number_input("纬度", value=st.session_state.point_b[0], format="%.6f", key="lb")
        with col2:
            lob = st.number_input("经度", value=st.session_state.point_b[1], format="%.6f", key="lob")
        if st.button("🏁 设置B点", use_container_width=True):
            st.session_state.point_b = [lb, lob]
            st.session_state.route_plans = []
            st.rerun()
        
        st.markdown("---")
        
        # 飞行高度
        st.markdown("### ⚙️ 飞行参数")
        alt = st.slider("飞行高度 (m)", 10, 150, st.session_state.flight_alt)
        st.session_state.flight_alt = alt
        
        # 高度冲突检测
        if st.session_state.obstacles:
            st.markdown("**📊 高度冲突检测**")
            for obs in st.session_state.obstacles:
                if alt < obs.min_h:
                    st.success(f"✅ 低于「{obs.name}」({obs.min_h}m)，将**绕行**")
                elif alt > obs.max_h:
                    st.success(f"✅ 高于「{obs.name}」({obs.max_h}m)，可**飞越**")
                else:
                    st.warning(f"⚠️ 与「{obs.name}」冲突 ({obs.min_h}-{obs.max_h}m)")
        
        st.markdown("---")
        
        # 障碍物列表
        st.markdown("### 🚧 障碍物列表")
        st.caption(f"共 {len(st.session_state.obstacles)} 个")
        for i, obs in enumerate(st.session_state.obstacles):
            if alt < obs.min_h:
                icon = "🔄"
            elif alt > obs.max_h:
                icon = "⬆️"
            else:
                icon = "⚠️"
            with st.expander(f"{icon} {obs.name} ({obs.min_h}-{obs.max_h}m)"):
                if st.button(f"删除", key=f"del_{i}"):
                    st.session_state.obstacles.pop(i)
                    st.session_state.route_plans = []
                    st.rerun()
        
        if st.button("🗑️ 清空全部", use_container_width=True):
            st.session_state.obstacles = []
            st.session_state.route_plans = []
            st.rerun()
        
        st.markdown("---")
        st.markdown("## 🗺️ 多航线规划")
        
        # 找碰撞障碍物
        def find_blocking(start, end):
            for obs in st.session_state.obstacles:
                if alt < obs.min_h:
                    for t in range(21):
                        t = t/20
                        lat = start[0] + (end[0]-start[0])*t
                        lon = start[1] + (end[1]-start[1])*t
                        if obs.contains([lat, lon]):
                            return obs
            return None
        
        # 生成方案按钮
        if st.button("🎯 生成航线方案", use_container_width=True, type="primary"):
            start = st.session_state.point_a
            end = st.session_state.point_b
            hit = find_blocking(start, end)
            
            plans = []
            if not hit:
                plans.append({
                    'name': '📏 直线路径',
                    'points': [start, end],
                    'dist': calc_distance(start, end),
                    'color': 'blue',
                    'desc': '✅ 无障碍物阻挡'
                })
            else:
                # 左绕行
                left = hit.get_left_bypass(start, end)
                left_dist = calc_distance(start, left) + calc_distance(left, end)
                plans.append({
                    'name': '⬅️ 左绕行',
                    'points': [start, left, end],
                    'dist': left_dist,
                    'color': 'orange',
                    'desc': f'从「{hit.name}」左侧绕过'
                })
                # 右绕行
                right = hit.get_right_bypass(start, end)
                right_dist = calc_distance(start, right) + calc_distance(right, end)
                plans.append({
                    'name': '➡️ 右绕行',
                    'points': [start, right, end],
                    'dist': right_dist,
                    'color': 'purple',
                    'desc': f'从「{hit.name}」右侧绕过'
                })
                # 最佳航线
                if left_dist <= right_dist:
                    plans.append({
                        'name': '⭐ 最佳航线',
                        'points': [start, left, end],
                        'dist': left_dist,
                        'color': 'gold',
                        'desc': f'最短路径，比另一方案节省{abs(left_dist-right_dist):.0f}m'
                    })
                else:
                    plans.append({
                        'name': '⭐ 最佳航线',
                        'points': [start, right, end],
                        'dist': right_dist,
                        'color': 'gold',
                        'desc': f'最短路径，比另一方案节省{abs(left_dist-right_dist):.0f}m'
                    })
            
            st.session_state.route_plans = plans
            if plans:
                st.session_state.selected_plan = plans[0]
            st.rerun()
        
        # 显示三个方案
        if st.session_state.route_plans:
            st.markdown("---")
            st.markdown("### 📋 可选方案")
            
            for i, p in enumerate(st.session_state.route_plans):
                col1, col2, col3 = st.columns([2, 1, 1])
                with col1:
                    if "左绕行" in p['name']:
                        st.markdown(f"**🟠 {p['name']}**")
                    elif "右绕行" in p['name']:
                        st.markdown(f"**🟣 {p['name']}**")
                    elif "最佳" in p['name']:
                        st.markdown(f"**⭐ {p['name']}**")
                    else:
                        st.markdown(f"**🔵 {p['name']}**")
                    st.caption(p['desc'])
                with col2:
                    st.metric("距离", f"{p['dist']:.0f}m")
                with col3:
                    st.metric("时间", f"{p['dist']/15:.0f}s")
                
                if st.session_state.selected_plan and st.session_state.selected_plan['name'] == p['name']:
                    st.success("✅ 已选中")
                else:
                    if st.button(f"选择此方案", key=f"sel_{i}", use_container_width=True):
                        st.session_state.selected_plan = p
                        st.rerun()
                st.markdown("---")
            
            if st.session_state.selected_plan:
                p = st.session_state.selected_plan
                st.info(f"**当前选中: {p['name']}** | 距离: {p['dist']:.0f}m | 时间: {p['dist']/15:.0f}s")
                if st.button("✈️ 确认使用此航线", use_container_width=True, type="primary"):
                    st.session_state.confirmed_plan = p
                    st.success(f"✅ 已确认使用 {p['name']}")
                    st.balloons()
        
        if st.session_state.confirmed_plan:
            st.markdown("---")
            st.markdown("### ✅ 当前航线")
            p = st.session_state.confirmed_plan
            st.success(f"**{p['name']}**")
            st.caption(f"总航程: {p['dist']:.0f}m | 预计时间: {p['dist']/15:.0f}s")

# ==================== Tab 2: 心跳监控 ====================
with tab2:
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("🚁 心跳控制")
        
        if not st.session_state.heartbeat_running:
            if st.button("▶️ 启动心跳模拟", type="primary", use_container_width=True):
                st.session_state.heartbeat_sim.start()
                st.session_state.heartbeat_running = True
                st.rerun()
        else:
            if st.button("⏹️ 停止心跳模拟", use_container_width=True):
                st.session_state.heartbeat_sim.stop()
                st.session_state.heartbeat_running = False
                st.rerun()
        
        st.markdown("---")
        st.subheader("📊 实时心跳")
        
        hb = st.session_state.heartbeat_sim.update()
        if hb:
            if hb['status'] == 'timeout':
                st.error(f"⚠️ 连接超时！3秒未收到心跳")
            else:
                st.success(f"💓 心跳正常 | ID: {hb['id']} | 时间: {hb['time']} | 延迟: {hb['delay']}ms")
        
        stats = st.session_state.heartbeat_sim.get_stats()
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("总心跳", stats['total'])
        col_b.metric("超时次数", stats['timeout'])
        col_c.metric("成功率", f"{stats['rate']}%")
    
    with col2:
        st.subheader("📈 心跳记录")
        
        history = st.session_state.heartbeat_sim.get_history()
        if history:
            df = pd.DataFrame(history[-10:])
            df_display = df[['id', 'time', 'status']].copy()
            df_display.columns = ['序号', '时间', '状态']
            df_display['状态'] = df_display['状态'].apply(lambda x: '✅ 正常' if x == 'alive' else '🔴 超时')
            st.dataframe(df_display, use_container_width=True, hide_index=True)
            
            if len(history) > 1:
                df_chart = pd.DataFrame([{'id': h['id'], 'status': 1 if h['status'] == 'alive' else 0} for h in history[-30:]])
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=df_chart['id'], y=df_chart['status'], mode='lines+markers', name='状态'))
                fig.add_hline(y=0.5, line_dash="dash", line_color="red", annotation_text="超时阈值")
                fig.update_layout(title="心跳趋势", xaxis_title="序号", yaxis_title="状态 (1=正常, 0=超时)")
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("等待心跳数据，点击「启动心跳模拟」开始")

st.markdown("---")
st.caption("💡 **操作步骤**：① 在地图上画多边形 → ② 设置高度/名称 → ③ 点击「生成航线方案」→ ④ 选择左/右/最佳 → ⑤ 确认使用")

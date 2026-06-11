import streamlit as st
import folium
from streamlit_folium import st_folium
from folium import plugins
import math
import json
import os
import random
import time
from datetime import datetime
import pandas as pd
import plotly.graph_objects as go

# ==================== GCJ-02 坐标系转换 ====================
class CoordConverter:
    @staticmethod
    def convert_display_coords(lat, lon, from_type, to_type="WGS-84"):
        return lat, lon  # 简化版

# ==================== 页面配置 ====================
st.set_page_config(page_title="无人机智能监控系统", page_icon="🛰️", layout="wide")

CAMPUS_GCJ02 = [32.234097, 118.749413]
OBSTACLE_CONFIG_FILE = "obstacle_config.json"
WAYPOINT_CONFIG_FILE = "waypoint_config.json"

# ==================== 初始化 ====================
if 'obstacles' not in st.session_state:
    if os.path.exists(OBSTACLE_CONFIG_FILE):
        try:
            with open(OBSTACLE_CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                st.session_state.obstacles = data.get('obstacles', [])
        except:
            st.session_state.obstacles = []
    else:
        st.session_state.obstacles = []

if 'point_a' not in st.session_state:
    if os.path.exists(WAYPOINT_CONFIG_FILE):
        try:
            with open(WAYPOINT_CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                st.session_state.point_a = data.get('point_a', [32.2323, 118.749])
                st.session_state.point_b = data.get('point_b', [32.2344, 118.749])
        except:
            st.session_state.point_a = [32.2323, 118.749]
            st.session_state.point_b = [32.2344, 118.749]
    else:
        st.session_state.point_a = [32.2323, 118.749]
        st.session_state.point_b = [32.2344, 118.749]

if 'coord_type' not in st.session_state:
    st.session_state.coord_type = "GCJ-02"
if 'flight_alt' not in st.session_state:
    st.session_state.flight_alt = 20
if 'safe_radius' not in st.session_state:
    st.session_state.safe_radius = 5
if 'route_plans' not in st.session_state:
    st.session_state.route_plans = []
if 'selected_plan' not in st.session_state:
    st.session_state.selected_plan = None
if 'confirmed_plan' not in st.session_state:
    st.session_state.confirmed_plan = None
if 'temp_obs' not in st.session_state:
    st.session_state.temp_obs = None
if 'temp_height' not in st.session_state:
    st.session_state.temp_height = 50
if 'temp_name' not in st.session_state:
    st.session_state.temp_name = "建筑物"
if 'show_height_panel' not in st.session_state:
    st.session_state.show_height_panel = False

# ==================== 保存函数 ====================
def save_waypoints():
    data = {'save_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'point_a': st.session_state.point_a, 'point_b': st.session_state.point_b}
    with open(WAYPOINT_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def save_obstacles_to_file():
    data = {'save_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'obstacles': st.session_state.obstacles, 'count': len(st.session_state.obstacles)}
    with open(OBSTACLE_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return True

def load_obstacles_from_file():
    if os.path.exists(OBSTACLE_CONFIG_FILE):
        with open(OBSTACLE_CONFIG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            st.session_state.obstacles = data.get('obstacles', [])
        return True
    return False

def get_config_status():
    if os.path.exists(OBSTACLE_CONFIG_FILE):
        with open(OBSTACLE_CONFIG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {'exists': True, 'count': data.get('count', 0), 'save_time': data.get('save_time', '未知')}
    return {'exists': False, 'count': 0}

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
            heartbeat = {'id': len(self.history) + 1, 'time': datetime.now().strftime("%H:%M:%S"), 'status': 'alive', 'delay': round(random.uniform(5, 50), 2)}
            self.history.append(heartbeat)
            if len(self.history) > 50:
                self.history.pop(0)
            return heartbeat
        if elapsed > 3 and not self.offline:
            self.offline = True
            timeout = {'id': len(self.history) + 1, 'time': datetime.now().strftime("%H:%M:%S"), 'status': 'timeout', 'delay': 0}
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
if 'heartbeat_running' not in st.session_state:
    st.session_state.heartbeat_running = False

# ==================== 几何计算函数 ====================
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

def line_intersects_polygon(start, end, poly):
    for t in range(21):
        t = t/20
        lat = start[0] + (end[0]-start[0])*t
        lon = start[1] + (end[1]-start[1])*t
        if point_in_polygon([lat, lon], poly):
            return True
    return False

# ==================== 障碍物类 ====================
class Obstacle:
    def __init__(self, points, height, name):
        self.points = points
        self.height = height
        self.name = name
        lats = [p[0] for p in points]
        lons = [p[1] for p in points]
        self.min_lat = min(lats)
        self.max_lat = max(lats)
        self.min_lon = min(lons)
        self.max_lon = max(lons)
        self.center_lat = (self.min_lat + self.max_lat) / 2
        self.center_lon = (self.min_lon + self.max_lon) / 2
        
    def to_dict(self):
        return {'points': self.points, 'height': self.height, 'name': self.name}
    
    @classmethod
    def from_dict(cls, data):
        return cls(data['points'], data['height'], data['name'])
    
    def contains(self, point):
        return point_in_polygon(point, self.points)
    
    def get_bypass_points(self, start, end, safe_radius=5):
        """获取左右绕行点"""
        safe_deg = safe_radius / 111000
        
        # 计算障碍物宽度的一半
        half_width = (self.max_lon - self.min_lon) / 2
        
        # 计算从起点到终点的方向
        dx = end[1] - start[1]
        dy = end[0] - start[0]
        length = math.sqrt(dx*dx + dy*dy)
        if length > 0:
            dx /= length
            dy /= length
        
        # 垂直方向
        perp_x = -dy
        perp_y = dx
        
        # 绕行偏移量 = 障碍物半宽 + 安全半径 + 额外余量
        offset = half_width + safe_deg + 0.001
        
        # 左绕行点
        left_bypass = [self.center_lat + perp_y * offset, self.center_lon + perp_x * offset]
        # 右绕行点
        right_bypass = [self.center_lat - perp_y * offset, self.center_lon - perp_x * offset]
        
        return left_bypass, right_bypass

# ==================== 标题 ====================
st.title("🛰️ 无人机智能监控系统")
st.markdown("**南京科技职业学院** | 3D障碍物 | 多航线选择 | 心跳监控")
st.markdown("---")

# ==================== 侧边栏 ====================
with st.sidebar:
    st.subheader("🌐 坐标系设置")
    coord_type = st.selectbox("输入坐标系", ["WGS-84", "GCJ-02 (高德/百度)"])
    st.session_state.coord_type = "WGS-84" if coord_type == "WGS-84" else "GCJ-02"
    
    st.markdown("---")
    st.subheader("📊 系统状态")
    st.success("✅ 系统运行正常")
    config_status = get_config_status()
    if config_status['exists']:
        st.info(f"💾 障碍物配置\n共 {config_status['count']} 个 | {config_status['save_time']}")

# ==================== 标签页 ====================
tab1, tab2 = st.tabs(["🗺️ 航线规划", "💓 心跳监控"])

# ==================== Tab 1: 航线规划 ====================
with tab1:
    col_left, col_right = st.columns([1.5, 1])
    
    with col_left:
        st.subheader("🗺️ 卫星地图")
        
        m = folium.Map(location=CAMPUS_GCJ02, zoom_start=17, control_scale=True)
        folium.TileLayer('https://webst0{s}.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}',
                         attr='高德卫星', subdomains=['1','2','3','4']).add_to(m)
        folium.TileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
                         attr='OpenStreetMap', name='街道地图').add_to(m)
        folium.Marker(CAMPUS_GCJ02, popup="🏫 南京科技职业学院", icon=folium.Icon(color='red')).add_to(m)
        
        alt = st.session_state.flight_alt
        for obs_data in st.session_state.obstacles:
            if isinstance(obs_data, dict):
                points = obs_data['points']
                height = obs_data['height']
                name = obs_data['name']
            else:
                points = obs_data.points
                height = obs_data.height
                name = obs_data.name
            
            color = 'red' if alt < height else 'green'
            folium.Polygon(points, color=color, weight=2, fill=True, fill_color=color, fill_opacity=0.3,
                          popup=f"{name}\n高度: {height}m").add_to(m)
        
        folium.Marker(st.session_state.point_a, popup="🚁 起点A", icon=folium.Icon(color='green')).add_to(m)
        folium.Marker(st.session_state.point_b, popup="🎯 终点B", icon=folium.Icon(color='red')).add_to(m)
        
        if st.session_state.selected_plan:
            p = st.session_state.selected_plan
            folium.PolyLine(p['points'], color=p['color'], weight=4).add_to(m)
            if len(p['points']) > 2:
                folium.Marker(p['points'][1], popup="绕行点", icon=folium.Icon(color='purple')).add_to(m)
        
        plugins.Draw(draw_options={'polygon': {'allowIntersection': False}}).add_to(m)
        plugins.MeasureControl().add_to(m)
        folium.LayerControl().add_to(m)
        
        output = st_folium(m, width=650, height=450, key="map")
        
        if output and output.get('last_active_drawing'):
            d = output['last_active_drawing']
            if d and d['geometry']['type'] == 'Polygon':
                pts = [[c[1], c[0]] for c in d['geometry']['coordinates'][0]]
                if len(pts) >= 3:
                    st.session_state.temp_obs = pts
                    st.session_state.show_height_panel = True
                    st.success(f"✅ 已绘制 {len(pts)} 个点")
    
    with col_right:
        # 新建障碍物
        if st.session_state.show_height_panel and st.session_state.temp_obs:
            st.markdown("### 🆕 新建3D障碍物")
            name = st.text_input("名称", value=st.session_state.temp_name)
            st.session_state.temp_name = name if name else "建筑物"
            
            height = st.number_input("障碍物高度 (m)", value=st.session_state.temp_height, min_value=1, max_value=200, step=5)
            st.session_state.temp_height = height
            st.progress(min(1.0, height/200))
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ 保存", type="primary", use_container_width=True):
                    new_obs = {'points': st.session_state.temp_obs, 'height': height, 'name': st.session_state.temp_name}
                    st.session_state.obstacles.append(new_obs)
                    save_obstacles_to_file()
                    st.session_state.temp_obs = None
                    st.session_state.show_height_panel = False
                    st.rerun()
            with col2:
                if st.button("🗑️ 取消", use_container_width=True):
                    st.session_state.temp_obs = None
                    st.session_state.show_height_panel = False
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
            save_waypoints()
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
            save_waypoints()
            st.rerun()
        
        st.markdown("---")
        
        # 飞行参数
        st.markdown("### ⚙️ 飞行参数")
        alt = st.slider("无人机飞行高度 (m)", 10, 150, st.session_state.flight_alt)
        st.session_state.flight_alt = alt
        safe_radius = st.slider("安全半径 (m)", 1, 30, st.session_state.safe_radius)
        st.session_state.safe_radius = safe_radius
        
        # 高度检测
        if st.session_state.obstacles:
            st.markdown("**📊 高度检测**")
            for obs_data in st.session_state.obstacles:
                name = obs_data['name'] if isinstance(obs_data, dict) else obs_data.name
                height = obs_data['height'] if isinstance(obs_data, dict) else obs_data.height
                if alt < height:
                    st.warning(f"🔄 低于「{name}」({height}m)，将绕行")
                else:
                    st.success(f"✅ 高于「{name}」({height}m)，可飞越")
        
        st.markdown("---")
        
        # 障碍物列表
        st.markdown("### 🚧 障碍物列表")
        for i, obs_data in enumerate(st.session_state.obstacles):
            name = obs_data['name'] if isinstance(obs_data, dict) else obs_data.name
            height = obs_data['height'] if isinstance(obs_data, dict) else obs_data.height
            icon = "🔄" if alt < height else "⬆️"
            with st.expander(f"{icon} {name} (高度: {height}m)"):
                if st.button(f"删除", key=f"del_{i}"):
                    st.session_state.obstacles.pop(i)
                    save_obstacles_to_file()
                    st.rerun()
        
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("💾 保存配置", use_container_width=True):
                save_obstacles_to_file()
                st.success("已保存")
        with col2:
            if st.button("📂 加载配置", use_container_width=True):
                load_obstacles_from_file()
                st.rerun()
        with col3:
            if st.button("🗑️ 清空全部", use_container_width=True):
                st.session_state.obstacles = []
                save_obstacles_to_file()
                st.rerun()
        
        st.markdown("---")
        st.markdown("## 🗺️ 多航线规划")
        
        # 查找阻挡障碍物
        def find_blocking(start, end, obstacles, flight_alt):
            for obs_data in obstacles:
                points = obs_data['points'] if isinstance(obs_data, dict) else obs_data.points
                height = obs_data['height'] if isinstance(obs_data, dict) else obs_data.height
                if flight_alt < height:
                    if line_intersects_polygon(start, end, points):
                        if isinstance(obs_data, dict):
                            return Obstacle.from_dict(obs_data)
                        else:
                            return obs_data
            return None
        
        # 生成方案
        if st.button("🎯 生成航线方案", use_container_width=True, type="primary"):
            start = st.session_state.point_a
            end = st.session_state.point_b
            hit = find_blocking(start, end, st.session_state.obstacles, alt)
            
            straight_dist = calc_distance(start, end)
            plans = []
            
            if not hit:
                plans.append({'name': '📏 直线飞越', 'points': [start, end], 'dist': straight_dist, 'color': 'blue', 'desc': '✅ 无障碍物'})
            else:
                left, right = hit.get_bypass_points(start, end, safe_radius)
                
                # 左绕行
                left_dist = calc_distance(start, left) + calc_distance(left, end)
                plans.append({'name': '⬅️ 左绕行', 'points': [start, left, end], 'dist': left_dist, 'color': 'orange', 
                             'desc': f'左侧绕过 (多走{left_dist-straight_dist:.0f}m)'})
                
                # 右绕行
                right_dist = calc_distance(start, right) + calc_distance(right, end)
                plans.append({'name': '➡️ 右绕行', 'points': [start, right, end], 'dist': right_dist, 'color': 'purple',
                             'desc': f'右侧绕过 (多走{right_dist-straight_dist:.0f}m)'})
                
                # 最佳航线
                best = min(plans, key=lambda x: x['dist']).copy()
                best['name'] = '⭐ 最佳航线'
                best['color'] = 'gold'
                best['desc'] = f'最短路径 (省{abs(plans[0]["dist"] - plans[1]["dist"]):.0f}m)'
                plans.append(best)
            
            st.session_state.route_plans = plans
            st.session_state.selected_plan = plans[-1]  # 默认选中最佳
            st.rerun()
        
        # 显示方案
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
                straight = calc_distance(st.session_state.point_a, st.session_state.point_b)
                st.info(f"**当前: {p['name']}** | {p['dist']:.0f}m | 比直线多走: {p['dist']-straight:.0f}m")
                if st.button("✈️ 确认使用", use_container_width=True, type="primary"):
                    st.session_state.confirmed_plan = p
                    st.success(f"✅ 已确认")
                    st.balloons()
        
        if st.session_state.confirmed_plan:
            st.markdown("---")
            st.markdown("### ✅ 当前航线")
            p = st.session_state.confirmed_plan
            st.success(f"**{p['name']}**")
            st.caption(f"距离: {p['dist']:.0f}m | 时间: {p['dist']/15:.0f}s")

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
                st.success(f"💓 心跳正常 | ID: {hb['id']} | 延迟: {hb['delay']}ms")
        
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
                fig.update_layout(title="心跳趋势", xaxis_title="序号", yaxis_title="状态")
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("等待心跳数据")

st.markdown("---")
st.caption("💡 **步骤**: ①画多边形 → ②设置高度 → ③生成方案 → ④选择 → ⑤确认")

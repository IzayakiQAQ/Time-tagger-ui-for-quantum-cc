import time
try:
    import TimeTagger
except ImportError:
    print("TimeTagger 库未找到。请确保处于正确的 Swabian 运行环境中。")
    exit(1)

def start_transmitter():
    # 1. 创建本地 TDC 连接
    print("正在连接本地 TimeTagger 发射节点...")
    try:
        tagger = TimeTagger.createTimeTagger()
        print(f"成功连接至 TDC 序列号: {tagger.getSerial()}")
    except Exception as e:
        print(f"连接失败: {e}")
        return
    
    # 2. 强制将时钟源设为外部 10MHz
    # 对于异地无光纤的局域网架构，物理时间对齐必须靠 GPSDO 输入 10MHz 来统一硬件时钟流速
    try:
        tagger.setClockSource(TimeTagger.ClockSource.External10MHz)
        print("已成功将硬件时钟源设定为: External 10MHz.")
    except Exception as e:
        print(f"警告：无法切换至外部 10MHz 时钟源。请检查设备后面板是否已接入参考信号！错误: {e}")
    
    # 3. 将此 TDC 的原始数据流通过网络端口向无线局域网络暴露出去
    port = 4444
    try:
        tagger.startServer(port)
        print(f"=================================================")
        print(f"Tagger 网络直播服务器已启动！ (监听端口: {port})")
        print(f"正在等待异地 Central UI 节点通过 WLAN 建立连接拉取数据...")
        print(f"请确保本机的 Windows 防火墙已放行 TCP {port} 端口。")
        print(f"=================================================")
    except Exception as e:
        print(f"启动网络服务器失败: {e}")
        TimeTagger.freeTimeTagger(tagger)
        return
    
    # 4. 挂起主线程保护服务器存活状态
    try:
        while True:
            # 此处可以加入定时打印本地计数率的调试信息
            time.sleep(5)
    except KeyboardInterrupt:
        print("\n收到用户中止指令，正在关闭服务器...")
    
    # 5. 安全退出
    tagger.stopServer()
    TimeTagger.freeTimeTagger(tagger)
    print("发射节点已安全离线。")

if __name__ == '__main__':
    start_transmitter()

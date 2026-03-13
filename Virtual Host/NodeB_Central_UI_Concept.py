import time
try:
    import TimeTagger
except ImportError:
    print("TimeTagger 库未找到。请确保处于正确的 Swabian 运行环境中。")
    exit(1)

# ==================== 网络配置区 ====================
REMOTE_NODE_IP = "192.168.1.100"  # 替换成 Node A (发射端) 在 WLAN 中的真实 IP 地址
REMOTE_PORT = 4444

# PPS 物理同步通道配置 (非常关键)
# 此配置告诉机器，硬件面板上接了 GPS 1PPS 信号的是哪个输入口
LOCAL_PPS_CHANNEL = 8    # 本地主控节点 TDC_B 背板接 1PPS 的通道
REMOTE_PPS_CHANNEL = 8   # 远端发射节点 TDC_A 背板接 1PPS 的通道
# ====================================================

def initialize_virtual_1tdc():
    """
    该函数演示如何在中枢电脑上，把本地硬件与 WLAN 传来的异地硬件，
    缝合成一台逻辑上完全等效的超级 1TDC 设备供 UI 使用。
    """
    print("==== 异地融合 Central 阶段开始 ====")
    
    # 1. 挂载远端 TDC (通过网线/WLAN 拉取流)
    print(f"1. 正在尝试联机拉取远端节点 {REMOTE_NODE_IP}:{REMOTE_PORT} 的数据流...")
    try:
        net_tagger = TimeTagger.createTimeTaggerNetwork(f"{REMOTE_NODE_IP}:{REMOTE_PORT}")
        print(f"--> [成功] 获取到远端 TDC 序列号: {net_tagger.getSerial()}")
    except Exception as e:
        print(f"--> [失败] 无法连入远端网络。请检查 WLAN 连通性和目标防火墙。({e})")
        return None, None, None

    # 2. 挂载本地 TDC
    print("\n2. 正在初始化本地 TDC_B ...")
    try:
        local_tagger = TimeTagger.createTimeTagger()
        local_tagger.setClockSource(TimeTagger.ClockSource.External10MHz)
        print(f"--> [成功] 本地 TDC 已锁定至外接 10MHz 时钟。")
    except Exception as e:
        print(f"--> [失败] 本地设备初始化异常。({e})")
        TimeTagger.freeTimeTagger(net_tagger)
        return None, None, None
        
    # 3. 施瓦本虚拟时空缝合 (Synchronizer)
    print("\n3. 启动 Swabian 宏观时间同步器 (PPS Synchronizer)...")
    try:
        # 激活同步器，强行抹平 WLAN 带来的乱序与延迟差 
        # 它会在内存中将两台独立设备的 1PPS 戳强制数学对齐
        synchronizer = TimeTagger.Synchronizer(
            tagger_master=local_tagger,         # 把本地机器当做时间轴绝对主盘
            master_channel=LOCAL_PPS_CHANNEL,   
            tagger_slave=net_tagger,            # 把远端来的流当做从盘拉拽时间
            slave_channel=REMOTE_PPS_CHANNEL
        )
        print(f"--> [成功] 时间同步器正在运行...")
        print(f"--> [核心状态] 两台设备在逻辑上已完全合并！")
    except Exception as e:
        print(f"--> [失败] 无法建立同步器。({e})")
        TimeTagger.freeTimeTagger(local_tagger)
        TimeTagger.freeTimeTagger(net_tagger)
        return None, None, None
        
    print("===================================")
    print("初始化完成！此时的 local_tagger 其实已经是一个拥有双倍通道的超级 1TDC。")
    print("远端的通道通常会被映射为 (原始通道号)。如果要做符合，直接像以往使用单一设备一样操作。")
    print("===================================")
    
    # 最终返回打包好的硬件组，原本的 UI 脚本里直接套用 local_tagger 实例即可。
    return local_tagger, net_tagger, synchronizer

def main():
    tagger_core, tagger_node_a, sync_engine = initialize_virtual_1tdc()
    
    if tagger_core is None:
        print("核心初始化失败，退出。")
        return
        
    try:
        print("主控中枢待机中，监控同步差值流 (按 Ctrl+C 终止)...")
        while True:
            time.sleep(1)
            # 在实际工程中，这里接下来就是唤起类似 ui timestamp 1TDC.py 的 QApplication 主界面
            # 然后把 tagger_core 扔进 ExperimentWorker 去做 Auto Search
    except KeyboardInterrupt:
        pass
    finally:
        # 清除资源，必须按照特定顺序释放，先释放同步器
        TimeTagger.freeTimeTagger(sync_engine)
        TimeTagger.freeTimeTagger(tagger_core)
        TimeTagger.freeTimeTagger(tagger_node_a)

if __name__ == '__main__':
    main()

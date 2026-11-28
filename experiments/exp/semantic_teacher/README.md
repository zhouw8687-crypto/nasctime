# 首轮语义教师与候选后果预测

`release.py` 将同前缀仿真分叉转成每决策一行的样本，保留域状态、截止时间、业务作用域、评价窗口、动作结果与偏好。历史 PF/目标 UE0 的数据是 100 ms 终端评价窗，补充优先类负载使用相同协议。场景组 v1.0 有自己的固定执行前缀、100 ms 局部控制窗口和约 500 ms 业务评价窗。用 `import_scenes.py` 从场景组的原始根目录导入，逐候选核对分叉前观测和回执，再在这些前缀上调用解析 GCC，模型估计与仿真实测分开。场景组无动作前缀没有滚动 GCC 轨迹。

发布时保留 `split-v1.json`，导入场景组采用其冻结的完整轨迹分组。无论候选和偏好数量，所有同前缀动作都留在该组。每条记录的 `semantic`、`scenario_context` 与 `intent` 是可因果取得的输入。预测器读取队列三档和关键业务类积压、目标 UE 带时信息、UPF 当前输入与容量、公开的业务与场景配置、候选动作。按配置预知扰动的起止属于当前实验条件。完整原始计数也保留供编码方案比较。

`predict.py` 是 NumPy 的多输出二阶岭回归。训练集拟合标准化和参数，验证集选正则化和可行阈值，留出集只跑最终评估。报告同时给出实测假可行的两个分母、误拒绝、因不可行产生的选择错误，以及按三套偏好归一化的有效选择损失。固定偏好定义见版本合同，业务和资源均以 100 ms 等效量归一，控制按期率采用百分比点误差。连续的效用损失只在实测可行选择上平均，实测不可行单列。等价和支配使用实测目标向量，资源与业务方向冲突保留为取舍。

从 `experiments/exp` 运行。输入路径均用绝对路径或本目录路径。

    python3 -B -m semantic_teacher.import_scenes "$scenes_v1_dev" "$normalized_dev"
    python3 -B -m semantic_teacher.import_scenes "$scenes_v1_heldout" "$normalized_heldout"
    python3 -B -m semantic_teacher.release --version 0.2.0 --source-revision 1771188,ae5f463,5817727 \
      --out "$release" "$original" "$near" "$over" "$normalized_dev" "$normalized_heldout"
    OPENBLAS_NUM_THREADS=1 python3 -B -m semantic_teacher.predict "$release" "$new_model_dir"
    python3 -B -m unittest semantic_teacher.test_predict counterfactual_teacher.test_teacher

模型输出文件包含冻结参数、样本及文件哈希和留出评估。`predict(model, rows)` 接受没有终端结果的行用于评分。参数状态可由 `np.load(model_path)` 读取。当前证据支持已测工况下的离线后果与动作选择评价，仍需闭环接入、上报链路时延和跨拓扑测试。

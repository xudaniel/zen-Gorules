# 折扣审批 Demo

[简体中文](README.md) · [English](README.en.md)

英文版请导入 [discount-approval.en.json](../../test-data/discount-approval.en.json)，规则条件与中文版一致，输出英文审批结果。

这是 GoRules 在线编辑器中演示的三个审批规则，保存为可导入的 JDM 文件，并接入 Python 同步测试套件。

## 先在网页里试

1. 下载 [discount-approval.json](../../test-data/discount-approval.json)。
2. 打开 <https://editor.gorules.io/>，通过 Open 或导入按钮选择该 JSON 文件。
3. 打开 Simulator，在左侧 Request 输入 `{"discount": 8}`。
4. 点击 **Run**，在右侧 **Output** 查看 `销售经理审批`。
5. 将数字改为 `3` 或 `15`，再次点击 **Run**。

`discount: 8` 表示折扣 **8%**，不是 `0.08`。Request 需要完整的 JSON；右侧 Input/Output 用来查看运行数据。

## 规则

| 顺序 | discount 条件 | approval 结果 |
|---|---|---|
| 1 | `<= 5` | 自动通过 |
| 2 | `<= 10` | 销售经理审批 |
| 3 | `> 10` | 总经理审批 |

命中策略是 **First**：从上往下，只采用第一条匹配规则。因此 3 同时满足前两行时，结果仍是“自动通过”。开启 `passThrough`，输出保留输入的 `discount`。

这与网页演示的规则一致：假定输入是 0–100 之间的数字，没有增加缺失值、类型或范围校验。这里只计算审批结果，不发送审批任务。

## 运行测试

在仓库根目录执行（已有构建好的 Python binding 环境可以跳过安装）：

```bash
python3 -m venv .temp/discount-approval-venv
source .temp/discount-approval-venv/bin/activate
python -m pip install zen-engine==2.0.2
python -m unittest bindings.python.test_sync.ZenEngine.test_discount_approval_demo -v
```

Windows 中将激活命令换成 `.temp\discount-approval-venv\Scripts\activate`。

上述命令使用发布的 `zen-engine==2.0.2`，不需要编译 Rust 源码。测试直接调用真实 ZEN 引擎，分别验证 `engine.evaluate` 和 `decision.evaluate` 的完整输出，没有用 Python 重写审批逻辑。成功时显示 `OK`；unittest 在一个测试方法中分别检查中英文各九个输入，共十八个子测试。

| 输入 discount | 预期 approval |
|---|---|
| 3 | 自动通过 |
| 8 | 销售经理审批 |
| 15 | 总经理审批 |
| 0 | 自动通过 |
| 5 | 自动通过 |
| 5.01 | 销售经理审批 |
| 10 | 销售经理审批 |
| 10.01 | 总经理审批 |
| 100 | 总经理审批 |

用例位于 JDM 文件的 `tests` 字段，属于测试元数据。自动化测试见 [test_sync.py](../../bindings/python/test_sync.py) 中的 `test_discount_approval_demo`；执行现有同步测试套件时也会包含它。

# 检索验证题库（冻结）

写于 2026-11-17，**在结构化开跑之前**，写题时未查看任何数据集内容。
这 20 条不得因验证结果而修改；要改就得重新记录一版并注明原因。

- 10 条「明显有对应」：峰哥的切片里应当能找到直接回答同类问题的片段
- 10 条「边缘/无对应」：人生话题之外的、或峰哥几乎不可能聊到的

判定阈值来自另一份 30 对 dev 集（不在本文件里），默认 0.62，见设计文档 §5.10。

```json
[
  {"query": "二十五岁还没找到方向，该不该先随便找份工作干着", "has_answer": true},
  {"query": "家里让我回小城市考编，我自己想去大城市闯，怎么选", "has_answer": true},
  {"query": "喜欢一个人但是对方一直不明确表态，还要不要继续", "has_answer": true},
  {"query": "工资不高又想存钱，有没有必要搞副业", "has_answer": true},
  {"query": "和父母关系很差，要不要干脆断了联系", "has_answer": true},
  {"query": "三十岁转行还来得及吗", "has_answer": true},
  {"query": "总觉得自己不如同龄人，很焦虑怎么办", "has_answer": true},
  {"query": "读研到底值不值，还是早点工作攒经验", "has_answer": true},
  {"query": "在工厂干流水线，感觉人生没希望了", "has_answer": true},
  {"query": "相亲市场里普通人还有机会吗", "has_answer": true},
  {"query": "量子计算机的退相干时间怎么做实验测量", "has_answer": false},
  {"query": "红烧肉先焯水还是先煸炒", "has_answer": false},
  {"query": "怎么给猫剪指甲它才不反抗", "has_answer": false},
  {"query": "Python 的 GIL 在 3.13 有什么变化", "has_answer": false},
  {"query": "去冰岛自驾需要办什么签证", "has_answer": false},
  {"query": "腰椎间盘突出做微创手术风险大吗", "has_answer": false},
  {"query": "怎么评价陀思妥耶夫斯基的复调叙事", "has_answer": false},
  {"query": "考研数学三的线性代数该怎么复习", "has_answer": false},
  {"query": "这只基金的年化收益率怎么算", "has_answer": false},
  {"query": "摄影棚里主光和辅光应该怎么布", "has_answer": false}
]
```

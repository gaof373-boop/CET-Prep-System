"""Crawler package: gather public-domain vocabulary + practice material.

Important
---------
CET-4/6 真题(含完整文章/题目/解析)的版权归教育部考试中心所有,
不允许整段抓取后入库再分发。本爬虫仅抓取:
  1. **公开的英语四六级词汇清单** (单词本身不受版权保护)
  2. **公共领域 / CC 协议的英语学习素材** (Wikipedia 等) 作为
     "练习材料" (在 UI 中明确标注,不是真题)

如果你的网络环境无法访问外部站点,本爬虫会自动回退到本地生成
数据并以 "synthetic" 标记,保证数据库始终有内容。
"""

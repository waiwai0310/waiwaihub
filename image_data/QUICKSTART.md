# 🚀 Quick Start Guide - 快速开始指南

## 30秒快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 测试单个产品(推荐先用这个测试!)
python main.py -a B08N5WRWNW

# 3. 查看结果
ls data/images/B08N5WRWNW/
```

就这么简单! 🎉

---

## ⚡ 常用命令速查

```bash
# 单个产品
python main.py -a B0DDTCQGTR

# 多个产品
python main.py -a B08N5WRWNW B07XJ8C8F5 B09G9FPHY6

# 从文件读取
python main.py -f asin_list.txt

# 日本站点
python main.py -a B08N5WRWNW -d jp

# 只下载主图
python main.py -a B08N5WRWNW -m 1

# 查看统计
python main.py --stats

# 查看错误
python main.py --recent-errors 20

# 清理日志
python main.py --cleanup-logs 30
```

---

## 📋 第一次使用流程

### Step 1: 创建ASIN列表
创建文件 `my_asins.txt`:
```
B08N5WRWNW
B07XJ8C8F5
B09G9FPHY6
```

### Step 2: 小规模测试
```bash
# 先测试前2个
python main.py -a B08N5WRWNW B07XJ8C8F5

# 查看日志确认没问题
tail logs/crawler.log
```

### Step 3: 检查结果
```bash
# 查看下载的图片
ls -lh data/images/B08N5WRWNW/

# 查看统计
python main.py --stats
```

### Step 4: 批量运行
```bash
# 如果测试成功,运行完整列表
python main.py -f my_asins.txt
```

---

## 🛡️ 安全检查清单

在大规模运行前,请确认:

- [ ] 已阅读 [SOP.md](SOP.md) 文档
- [ ] 已测试过2-3个产品且成功
- [ ] REQUEST_DELAY_MIN >= 2.0 秒
- [ ] RATE_LIMIT_CALLS <= 30
- [ ] 已准备好监控日志: `tail -f logs/crawler.log`
- [ ] 不是在高峰期运行(避开美国白天)
- [ ] 有足够的磁盘空间

---

## 🔧 遇到问题?

### 问题1: 安装失败
```bash
# 升级pip
pip install --upgrade pip

# 逐个安装
pip install requests beautifulsoup4 lxml
```

### 问题2: 429错误(太频繁)
修改 `config.py`:
```python
REQUEST_DELAY_MIN = 10.0  # 增加到10秒
REQUEST_DELAY_MAX = 20.0
RATE_LIMIT_CALLS = 10     # 降低到10
```

### 问题3: 没有找到图片
检查ASIN是否正确:
1. 手动访问: https://www.amazon.com/dp/B08N5WRWNW
2. 确认产品页面有图片
3. 查看日志: `tail logs/crawler.log`

---

## 📊 辅助工具

### 验证图片完整性
```bash
python verify_images.py
```

### 查看详细统计
```bash
python statistics.py

# 生成JSON报告
python statistics.py --json
```

---

## 🎯 推荐工作流

### 日常使用
```bash
# 1. 准备今天的ASIN列表
vim today_asins.txt

# 2. 运行爬虫(开启日志监控)
python main.py -f today_asins.txt &
tail -f logs/crawler.log

# 3. 完成后检查
python main.py --stats
python verify_images.py

# 4. 备份(可选)
tar -czf backup_$(date +%Y%m%d).tar.gz data/
```

### 定期维护
```bash
# 每周: 查看错误
python main.py --recent-errors 50

# 每月: 清理日志
python main.py --cleanup-logs 30

# 每月: 统计报告
python statistics.py --json
```

---

## 💡 专业技巧

### 技巧1: 分时段运行
```bash
# 使用cron在凌晨运行(美国时间)
# 编辑: crontab -e
0 3 * * * cd /path/to/crawler && python main.py -f daily_batch.txt
```

### 技巧2: 失败重试
```bash
# 第一次运行
python main.py -f all_asins.txt 2>&1 | tee run1.log

# 提取失败的ASIN(需要根据实际日志格式调整)
grep "Failed" logs/crawler.log | cut -d' ' -f5 > failed_asins.txt

# 第二天重试失败的
python main.py -f failed_asins.txt
```

### 技巧3: 监控进度
```bash
# 实时查看下载进度
watch -n 10 'find data/images -name "*.jpg" | wc -l'

# 查看当前速率
watch -n 30 'tail -20 logs/crawler.log | grep Success'
```

---

## ⚠️ 重要提醒

1. **安全第一**: 默认配置已经很保守,不要随意降低延迟
2. **小步快跑**: 从10个产品开始,逐步扩展
3. **监控日志**: 随时注意异常情况
4. **合法使用**: 仅用于市场研究,遵守Amazon条款

---

## 📚 更多信息

- 📖 完整文档: [SOP.md](SOP.md)
- 📋 使用说明: [README.md](README.md)
- 🐛 问题反馈: GitHub Issues

---

**祝你使用愉快! Good luck! 🚀**

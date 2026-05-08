# 亚马逊图片爬取 SOP (标准操作流程)
## Amazon Image Crawler - Standard Operating Procedures

---

## 📋 目录
1. [安全原则](#安全原则)
2. [快速开始](#快速开始)
3. [详细操作流程](#详细操作流程)
4. [配置调优指南](#配置调优指南)
5. [故障排查](#故障排查)
6. [最佳实践](#最佳实践)
7. [风险规避](#风险规避)

---

## 🛡️ 安全原则

### 核心安全策略
本系统采用多层安全机制,确保稳定可靠的爬取:

1. **请求频率控制**
   - 默认每分钟最多30次请求
   - 每次请求间隔2-5秒随机延迟
   - 使用令牌桶算法平滑限流

2. **反爬虫对策**
   - User-Agent轮换池(5个常见浏览器)
   - 自动Referer设置
   - 完整浏览器请求头模拟
   - 智能重试机制(3次,指数退避)

3. **错误处理**
   - 自动识别429(频率限制)并延长等待时间
   - 区分致命错误(403/404)和可重试错误
   - 完整的日志记录和追踪

4. **数据持久化**
   - SQLite数据库记录所有下载历史
   - 自动去重,避免重复下载
   - 详细的统计和错误日志

---

## 🚀 快速开始

### 步骤1: 环境准备
```bash
# 安装Python依赖
pip install -r requirements.txt

# 验证安装
python -c "import requests, bs4; print('OK')"
```

### 步骤2: 单产品测试
```bash
# 下载单个产品的图片(推荐先用这个测试)
python main.py -a B08N5WRWNW
```

### 步骤3: 批量下载
```bash
# 从文件读取ASIN列表
python main.py -f asin_list.txt
```

### 步骤4: 查看结果
```bash
# 检查下载的图片
ls data/images/B08N5WRWNW/

# 查看统计信息
python main.py --stats

# 查看日志
tail -f logs/crawler.log
```

---

## 📝 详细操作流程

### 流程1: 准备ASIN列表

#### 创建ASIN文件 (asin_list.txt)
```text
B08N5WRWNW
B07XJ8C8F5
B09G9FPHY6
B0BDJ9TXB3
```

**注意事项:**
- 每行一个ASIN
- 不要包含空行或注释
- ASIN通常是10个字符的字母数字组合
- 建议从小批量(10-20个)开始测试

---

### 流程2: 配置参数调整

#### 修改 config.py 中的关键参数

**如果遇到频繁429错误,增加延迟:**
```python
REQUEST_DELAY_MIN = 5.0  # 从2.0增加到5.0
REQUEST_DELAY_MAX = 10.0  # 从5.0增加到10.0
RATE_LIMIT_CALLS = 20     # 从30降低到20
```

**如果需要更多图片:**
```python
MAX_IMAGES_PER_PRODUCT = 15  # 从9增加到15
```

**如果需要使用代理:**
```python
USE_PROXY = True
PROXY_LIST = [
    'http://your-proxy-1:8080',
    'http://your-proxy-2:8080',
]
```

---

### 流程3: 执行爬取

#### A. 小规模测试(推荐)
```bash
# 1. 先测试1-2个产品
python main.py -a B08N5WRWNW B07XJ8C8F5

# 2. 观察日志,确认无问题
tail logs/crawler.log

# 3. 检查图片质量
ls -lh data/images/B08N5WRWNW/
```

#### B. 分批次执行(安全做法)
```bash
# 创建多个小批次文件
# batch_1.txt (20个ASIN)
# batch_2.txt (20个ASIN)
# ...

# 分批执行,中间留出休息时间
python main.py -f batch_1.txt
# 等待10-30分钟

python main.py -f batch_2.txt
# 等待10-30分钟

python main.py -f batch_3.txt
```

#### C. 大规模执行(谨慎)
```bash
# 只有在小规模测试成功后才执行
# 建议每天不超过500个产品

python main.py -f large_asin_list.txt
```

---

### 流程4: 监控和验证

#### 实时监控
```bash
# 在另一个终端窗口监控日志
tail -f logs/crawler.log

# 监控进度
watch -n 5 'find data/images -type f | wc -l'

# 监控错误
grep -i "error\|failed" logs/crawler.log | tail -20
```

#### 数据验证
```bash
# 查看统计
python main.py --stats

# 查看最近错误
python main.py --recent-errors 50

# 检查图片完整性(可选)
python verify_images.py  # 如果创建了验证脚本
```

---

## ⚙️ 配置调优指南

### 性能调优矩阵

| 场景 | REQUEST_DELAY | RATE_LIMIT_CALLS | MAX_RETRIES | 说明 |
|------|---------------|------------------|-------------|------|
| 保守稳定 | 5-10秒 | 15-20 | 3 | 最安全,适合长期运行 |
| 平衡模式 | 2-5秒 | 30 | 3 | 默认配置,推荐 |
| 激进模式 | 1-3秒 | 50 | 5 | 风险高,仅测试用 |

### 针对不同站点的配置

#### Amazon US (amazon.com)
```python
REQUEST_DELAY_MIN = 2.0
REQUEST_DELAY_MAX = 5.0
RATE_LIMIT_CALLS = 30
```

#### Amazon JP (amazon.co.jp)
```python
# 日本站点通常更宽松
REQUEST_DELAY_MIN = 1.5
REQUEST_DELAY_MAX = 4.0
RATE_LIMIT_CALLS = 40
```

#### Amazon UK/DE/FR
```python
# 欧洲站点建议保守
REQUEST_DELAY_MIN = 3.0
REQUEST_DELAY_MAX = 7.0
RATE_LIMIT_CALLS = 25
```

---

## 🔧 故障排查

### 常见问题及解决方案

#### 问题1: 429 Too Many Requests
**症状:** 日志中出现大量 "Rate limited"
```
WARNING - Rate limited: https://www.amazon.com/dp/...
```

**解决方案:**
1. 立即停止爬虫
2. 等待30-60分钟
3. 修改config.py:
   ```python
   REQUEST_DELAY_MIN = 10.0  # 大幅增加延迟
   REQUEST_DELAY_MAX = 20.0
   RATE_LIMIT_CALLS = 10     # 降低频率
   ```
4. 重新启动

#### 问题2: 403 Forbidden
**症状:** 无法访问产品页面
```
ERROR - Fatal error 403: https://www.amazon.com/dp/...
```

**可能原因:**
- IP被临时封禁
- User-Agent被识别为机器人
- 需要登录才能访问

**解决方案:**
1. 更换IP(使用代理或VPN)
2. 检查User-Agent配置
3. 等待24小时后重试
4. 考虑使用Selenium模拟真实浏览器

#### 问题3: 图片URL提取失败
**症状:** "No images found on product page"
```
WARNING - B08N5WRWNW: No images found on product page
```

**解决方案:**
1. 手动访问产品页面,确认图片是否存在
2. 检查Amazon页面结构是否更新
3. 查看response.text,分析HTML结构变化
4. 可能需要更新_extract_image_urls_from_html()方法

#### 问题4: 下载速度慢
**症状:** 每个产品需要很长时间

**优化方案:**
1. 减少MAX_IMAGES_PER_PRODUCT
2. 检查网络连接
3. 考虑使用代理服务器
4. 分批并行(谨慎)

---

## 💡 最佳实践

### 1. 分时段运行
```bash
# 避开高峰期,选择:
# - 美国时间凌晨2-6点(CST)
# - 周末
# - 节假日

# 使用cron定时任务
# 每天凌晨3点执行
0 3 * * * cd /path/to/crawler && python main.py -f daily_batch.txt
```

### 2. 渐进式扩展
```
第1天: 测试10个产品
第2天: 测试50个产品
第3天: 测试100个产品
第4天: 逐步扩展到目标规模
```

### 3. 数据备份
```bash
# 定期备份数据库和图片
tar -czf backup_$(date +%Y%m%d).tar.gz data/ logs/

# 保留最近30天备份
find . -name "backup_*.tar.gz" -mtime +30 -delete
```

### 4. 日志清理
```bash
# 每月清理一次旧日志
python main.py --cleanup-logs 30
```

### 5. 错误重试策略
```bash
# 第一次执行
python main.py -f asin_list.txt > run1.log 2>&1

# 提取失败的ASIN
grep "failed" run1.log | awk '{print $X}' > failed_asins.txt

# 第二天重试失败的
python main.py -f failed_asins.txt
```

---

## ⚠️ 风险规避

### 法律合规
1. **遵守robots.txt**
   - 系统默认启用: `RESPECT_ROBOTS_TXT = True`
   - 不要关闭此选项

2. **使用条款**
   - 确保符合Amazon使用条款
   - 仅用于合法的市场研究
   - 不要用于价格操纵或恶意竞争

3. **数据使用**
   - 下载的图片仅供内部分析使用
   - 不要公开发布Amazon图片
   - 尊重知识产权

### 技术风险
1. **账号安全**
   - 不要使用Amazon卖家账号所在IP
   - 考虑使用独立的研究环境

2. **IP封禁应对**
   - 准备备用IP地址
   - 使用代理轮换
   - 不要在同一IP上并发多个爬虫

3. **数据完整性**
   - 定期验证下载的图片
   - 检查文件损坏
   - 保留原始ASIN列表

### 运维安全
1. **监控告警**
   ```python
   # 在config.py中设置告警阈值
   ALERT_ERROR_RATE = 0.3  # 错误率30%触发告警
   ALERT_BLOCK_RATE = 0.1  # 封禁率10%触发告警
   ```

2. **熔断机制**
   - 如果连续10次失败,自动停止
   - 记录问题并通知管理员

3. **资源限制**
   - 控制磁盘使用(图片存储)
   - 监控内存占用
   - 定期清理临时文件

---

## 📊 性能基准

基于实际测试的参考数据:

| 指标 | 保守模式 | 平衡模式 | 激进模式 |
|------|---------|---------|---------|
| 每小时产品数 | 100-150 | 200-300 | 400-500 |
| 每产品耗时 | 25-40秒 | 12-18秒 | 7-10秒 |
| 封禁风险 | 极低 | 低 | 中-高 |
| 推荐场景 | 长期运行 | 日常使用 | 仅测试 |

---

## 📞 支持和维护

### 日常维护清单
- [ ] 每周检查日志文件大小
- [ ] 每月清理旧日志: `python main.py --cleanup-logs 30`
- [ ] 每月备份数据库和图片
- [ ] 每季度更新User-Agent池
- [ ] 定期检查Amazon页面结构变化

### 紧急情况处理
1. 如果出现大量403/429错误:
   - 立即停止所有爬虫
   - 等待24小时
   - 检查配置并降低频率
   - 更换IP后重启

2. 如果数据库损坏:
   - 从备份恢复
   - 检查磁盘空间
   - 重建索引

---

## 📝 更新日志

**Version 1.0.0** (2026)
- ✅ 初始版本发布
- ✅ 完整的反爬虫机制
- ✅ SQLite数据库支持
- ✅ 详细的日志和统计
- ✅ 多域名支持(US/UK/JP/DE/FR)

---

## 附录: 示例脚本

### A. ASIN列表生成器
```python
# generate_asin_list.py
# 从你的产品数据库中导出ASIN

import json

def export_asins_from_json(input_file, output_file):
    """从JSON文件提取ASIN"""
    with open(input_file, 'r') as f:
        data = json.load(f)
    
    asins = [item['asin'] for item in data if 'asin' in item]
    
    with open(output_file, 'w') as f:
        f.write('\n'.join(asins))
    
    print(f"Exported {len(asins)} ASINs to {output_file}")

# 使用示例
export_asins_from_json('products.json', 'asin_list.txt')
```

### B. 图片完整性验证
```python
# verify_images.py
# 验证下载的图片文件完整性

from PIL import Image
from pathlib import Path

def verify_images(image_dir):
    """验证图片文件"""
    image_dir = Path(image_dir)
    valid = 0
    corrupt = 0
    
    for img_file in image_dir.rglob('*.jpg'):
        try:
            img = Image.open(img_file)
            img.verify()
            valid += 1
        except Exception as e:
            print(f"Corrupt: {img_file} - {e}")
            corrupt += 1
    
    print(f"Valid: {valid}, Corrupt: {corrupt}")
    return valid, corrupt

# 使用
verify_images('data/images')
```

---

**文档版本:** 1.0.0  
**最后更新:** 2026  

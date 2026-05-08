#!/usr/bin/env python3
"""
投影仪评论分析配置文件诊断工具
功能:
1. 检测语义重复和冗余
2. 识别缺失的规则覆盖
3. 分析权重分布
4. 检测潜在的匹配冲突
5. 生成优化建议
"""

import json
import re
from collections import defaultdict, Counter
from typing import Dict, List, Set, Tuple

class ConfigAnalyzer:
    def __init__(self, config_path: str):
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        self.issues = []
        self.stats = {}
        
    def analyze(self):
        """运行所有分析"""
        print("🔍 开始分析配置文件...\n")
        
        self.check_regex_patterns()
        self.check_semantic_redundancy()
        self.check_coverage()
        self.check_weight_distribution()
        self.check_negation_handling()
        self.check_intensity_modifiers()
        self.generate_stats()
        
        return self.generate_report()
    
    def check_regex_patterns(self):
        """检查正则表达式"""
        print("📌 检查正则表达式...")
        
        # 检查prefix_pattern
        prefix = self.config['rules'].get('prefix_pattern', '')
        if '+' in prefix and not '*' in prefix:
            self.issues.append({
                'severity': 'HIGH',
                'category': '正则表达式错误',
                'location': 'rules.prefix_pattern',
                'issue': '使用了 + 而非 *,可能导致匹配失败',
                'suggestion': '将 + 改为 * 以支持零次或多次匹配'
            })
    
    def check_semantic_redundancy(self):
        """检查语义重复"""
        print("📌 检查语义重复...")
        
        exact_rules = self.config['rules'].get('exact_rules', {})
        
        for category, rules in exact_rules.items():
            # 统计相同的标签值
            label_counts = defaultdict(list)
            for keyword, label in rules.items():
                if isinstance(label, str):
                    label_counts[label].append(keyword)
                elif isinstance(label, dict):
                    label_counts[label.get('label', label)].append(keyword)
            
            # 找出重复的标签
            for label, keywords in label_counts.items():
                if len(keywords) > 5:  # 超过5个关键词映射到同一标签
                    self.issues.append({
                        'severity': 'MEDIUM',
                        'category': '近义词冗余',
                        'location': f'exact_rules.{category}',
                        'issue': f'标签"{label}"有{len(keywords)}个近义词',
                        'keywords': keywords,
                        'suggestion': f'考虑精简到3-5个核心关键词,其余通过keyword_rules处理'
                    })
    
    def check_coverage(self):
        """检查规则覆盖度"""
        print("📌 检查规则覆盖度...")
        
        exact_rules = self.config['rules'].get('exact_rules', {})
        keyword_rules = self.config['rules'].get('keyword_rules', {})
        
        # 检查哪些维度只有exact_rules但没有keyword_rules
        exact_categories = set(exact_rules.keys())
        keyword_categories = set(keyword_rules.keys())
        
        missing_keyword = exact_categories - keyword_categories
        if missing_keyword:
            for cat in missing_keyword:
                self.issues.append({
                    'severity': 'LOW',
                    'category': '覆盖度',
                    'location': f'keyword_rules',
                    'issue': f'维度"{cat}"缺少keyword_rules',
                    'suggestion': '添加关键词规则以提高召回率'
                })
    
    def check_weight_distribution(self):
        """检查权重分布"""
        print("📌 检查权重分布...")
        
        keyword_rules = self.config['rules'].get('keyword_rules', {})
        
        weights = []
        for category, rules in keyword_rules.items():
            weight = rules.get('权重', 1.0)
            weights.append((category, weight))
        
        # 检查权重是否都是1.0(未设置)
        if all(w == 1.0 for _, w in weights):
            self.issues.append({
                'severity': 'MEDIUM',
                'category': '权重系统',
                'location': 'keyword_rules',
                'issue': '所有维度权重都是1.0,未体现重要性差异',
                'suggestion': '为核心维度(亮度、清晰度、色彩)设置更高权重(1.2-1.3)'
            })
    
    def check_negation_handling(self):
        """检查否定词处理"""
        print("📌 检查否定词处理...")
        
        if 'negation_handler' not in self.config.get('semantic_engine', {}):
            self.issues.append({
                'severity': 'HIGH',
                'category': '语义引擎',
                'location': 'semantic_engine',
                'issue': '缺少否定词处理机制',
                'suggestion': '添加negation_handler配置,处理"不模糊"、"没有噪音"等表达',
                'impact': '可能导致误判率增加20-30%'
            })
    
    def check_intensity_modifiers(self):
        """检查程度词增强"""
        print("📌 检查程度词增强...")
        
        if 'intensity_modifier' not in self.config.get('semantic_engine', {}):
            self.issues.append({
                'severity': 'HIGH',
                'category': '语义引擎',
                'location': 'semantic_engine',
                'issue': '缺少程度词增强机制',
                'suggestion': '添加intensity_modifier配置,处理"非常"、"特别"等程度副词',
                'impact': '无法区分"模糊"和"非常模糊"的程度差异'
            })
    
    def generate_stats(self):
        """生成统计信息"""
        exact_rules = self.config['rules'].get('exact_rules', {})
        keyword_rules = self.config['rules'].get('keyword_rules', {})
        
        self.stats = {
            'total_exact_categories': len(exact_rules),
            'total_keyword_categories': len(keyword_rules),
            'total_exact_rules': sum(len(rules) for rules in exact_rules.values()),
            'total_keyword_rules': sum(
                len(rules.get('正面', [])) + len(rules.get('负面', []))
                for rules in keyword_rules.values()
            ),
            'avg_rules_per_category': sum(len(rules) for rules in exact_rules.values()) / len(exact_rules) if exact_rules else 0
        }
    
    def generate_report(self) -> Dict:
        """生成分析报告"""
        # 按严重程度排序
        severity_order = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}
        sorted_issues = sorted(self.issues, key=lambda x: severity_order[x['severity']])
        
        report = {
            'summary': {
                'total_issues': len(self.issues),
                'high_severity': len([i for i in self.issues if i['severity'] == 'HIGH']),
                'medium_severity': len([i for i in self.issues if i['severity'] == 'MEDIUM']),
                'low_severity': len([i for i in self.issues if i['severity'] == 'LOW'])
            },
            'statistics': self.stats,
            'issues': sorted_issues,
            'recommendations': self.generate_recommendations()
        }
        
        return report
    
    def generate_recommendations(self) -> List[str]:
        """生成优化建议"""
        recs = []
        
        high_issues = [i for i in self.issues if i['severity'] == 'HIGH']
        if high_issues:
            recs.append('🔥 紧急: 立即修复所有HIGH级别问题,这些会显著影响分类准确性')
        
        if self.stats.get('avg_rules_per_category', 0) > 15:
            recs.append('📝 建议: 平均每个维度规则过多,考虑精简和标准化')
        
        if 'negation_handler' not in self.config.get('semantic_engine', {}):
            recs.append('⚙️  建议: 优先实现否定词处理引擎,预计可提升15-20%准确率')
        
        return recs

def print_report(report: Dict):
    """打印美化的报告"""
    print("\n" + "="*80)
    print("配置文件分析报告".center(80))
    print("="*80 + "\n")
    
    # 汇总
    summary = report['summary']
    print("📊 问题汇总")
    print(f"   总问题数: {summary['total_issues']}")
    print(f"   🔴 严重: {summary['high_severity']}")
    print(f"   🟡 中等: {summary['medium_severity']}")
    print(f"   🟢 轻微: {summary['low_severity']}\n")
    
    # 统计
    stats = report['statistics']
    print("📈 配置统计")
    print(f"   精确匹配维度: {stats['total_exact_categories']}")
    print(f"   关键词匹配维度: {stats['total_keyword_categories']}")
    print(f"   精确匹配规则总数: {stats['total_exact_rules']}")
    print(f"   关键词规则总数: {stats['total_keyword_rules']}")
    print(f"   平均每维度规则数: {stats['avg_rules_per_category']:.1f}\n")
    
    # 问题详情
    print("🔍 问题详情\n")
    for i, issue in enumerate(report['issues'], 1):
        severity_emoji = {'HIGH': '🔴', 'MEDIUM': '🟡', 'LOW': '🟢'}
        print(f"{i}. {severity_emoji[issue['severity']]} [{issue['category']}] {issue['location']}")
        print(f"   问题: {issue['issue']}")
        print(f"   建议: {issue['suggestion']}")
        if 'impact' in issue:
            print(f"   影响: {issue['impact']}")
        print()
    
    # 建议
    if report['recommendations']:
        print("💡 优化建议\n")
        for rec in report['recommendations']:
            print(f"   {rec}")
        print()

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python config_analyzer.py <config.json>")
        sys.exit(1)
    
    analyzer = ConfigAnalyzer(sys.argv[1])
    report = analyzer.analyze()
    print_report(report)
    
    # 保存JSON报告
    report_path = 'analysis_report.json'
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print(f"\n详细报告已保存到: {report_path}")

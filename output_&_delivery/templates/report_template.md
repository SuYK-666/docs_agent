# {{ title }}

**发文部门：** {{ issuing_department }}  
**文号：** {{ document_no }}  
**发布日期：** {{ publish_date }}  
**公文类型：** {{ doc_type }}

## 核心摘要

{% for line in summary_lines %}> {{ line }}
{% endfor %}

{% if warning %}

## ⚠ 抓取失败告警

> {{ warning }}
{% if crawl_error_url %}> 原链接：{{ crawl_error_url }}
{% endif %}
{% if crawl_error_reason %}> 失败原因：{{ crawl_error_reason }}
{% endif %}
{% endif %}

## 待办清单

{% for task in tasks %}

- [ ] **{{ task.task_name }}**  
  责任人：{{ task.owner }}  
  截止：{{ task.deadline_display }}  
  执行动作：{{ task.action_suggestion }}  
  交付物：{% if task.deliverables %}{{ task.deliverables | join('；') }}{% else %}未提及{% endif %}  
  > 🔍 原文出处（{{ task.source_anchor.block_id }}）：{{ task.source_anchor.quote }}

{% endfor %}

{% if not tasks %}

- 当前条目未生成可执行任务（可能为抓取失败告警）。

{% endif %}

## 风险与追问

### 风险提示

{% if risks_or_unclear_points %}{% for risk in risks_or_unclear_points %}{{ loop.index }}. {{ risk }}
{% endfor %}{% else %}1. 暂未识别到明显风险。
{% endif %}

### 跟进问题

{% if follow_up_questions %}{% for question in follow_up_questions %}{{ loop.index }}. {{ question }}
{% endfor %}{% else %}1. 暂无补充追问。
{% endif %}

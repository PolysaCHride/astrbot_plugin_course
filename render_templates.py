DAY_TMPL = r"""
<!doctype html>
<html lang="zh">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width={{ page_width | default(500) }}, initial-scale=1" />
  <style>
    :root {
      --bg: #ffffff;
      --text-main: #1e293b;
      --text-muted: #64748b;
      --accent: #3b82f6;
      --accent-soft: #eff6ff;
      --card-bg: #f8fafc;
      --border: #e2e8f0;
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html {
      width: fit-content;
      background: var(--bg);
    }
    body {
      background: var(--bg);
      font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
      width: {{ page_width | default(500) }}px;
    }
    .container {
      padding: 24px;
      background: var(--bg);
    }
    .header {
      margin-bottom: 24px;
      padding-bottom: 16px;
      border-bottom: 2px solid var(--accent-soft);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .title-group h1 {
      font-size: 28px;
      font-weight: 900;
      color: var(--text-main);
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .date-badge {
      font-size: 14px;
      color: var(--accent);
      font-weight: 700;
      background: var(--accent-soft);
      padding: 4px 12px;
      border-radius: 8px;
    }

    .course-stack { display: flex; flex-direction: column; gap: 12px; }
    .course-card {
      background: var(--card-bg);
      border-radius: 16px;
      padding: 16px;
      display: flex;
      gap: 16px;
      border: 1px solid var(--border);
    }
    .time-slot {
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: center;
      min-width: 80px;
      padding-right: 16px;
      border-right: 2px dashed var(--border);
    }
    .time-start { font-size: 18px; font-weight: 800; color: var(--accent); }
    .time-end { font-size: 12px; font-weight: 600; color: var(--text-muted); margin-top: 2px; }
    
    .course-info { flex: 1; display: flex; flex-direction: column; justify-content: center; }
    .course-name { font-size: 19px; font-weight: 800; color: var(--text-main); margin-bottom: 6px; line-height: 1.3; }
    .meta-item { display: flex; align-items: center; gap: 4px; font-size: 14px; color: var(--text-muted); font-weight: 600; }

    .empty-state {
      padding: 40px 20px;
      text-align: center;
      border: 2px dashed var(--border);
      border-radius: 20px;
      color: var(--text-muted);
    }
    .empty-icon { font-size: 40px; margin-bottom: 10px; display: block; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="title-group">
        <h1>📅 {{ title }}</h1>
      </div>
      <div class="date-badge">{{ subtitle.split(' | ')[1] }}</div>
    </div>
    <div class="course-stack">
      {% if courses|length == 0 %}
        <div class="empty-state">
          <span class="empty-icon">🌟</span>
          <p>今日暂无课程，享受生活吧</p>
        </div>
      {% else %}
        {% for c in courses %}
          <div class="course-card">
            <div class="time-slot">
              <span class="time-start">{{ c.time_range.split(' - ')[0] }}</span>
              <span class="time-end">{{ c.time_range.split(' - ')[1] }}</span>
            </div>
            <div class="course-info">
              <div class="course-name">{{ c.summary }}</div>
              <div class="meta-item">📍 {{ c.location if c.location else "待定地点" }}</div>
            </div>
          </div>
        {% endfor %}
      {% endif %}
    </div>
  </div>
</body>
</html>
"""

WEEK_TMPL = r"""
<!doctype html>
<html lang="zh">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=480, initial-scale=1" />
  <style>
    :root {
      --bg: #f8fafc;
      --text-main: #1e293b;
      --text-muted: #94a3b8;
      --accent: #3b82f6;
      --today-bg: #eff6ff;
      --border: #e2e8f0;
      --card-bg: #ffffff;
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      background: var(--bg);
      font-family: 'PingFang SC', sans-serif;
      width: 480px;
      padding-bottom: 30px;
    }
    .container { padding: 20px; }
    .title-area { 
      margin-bottom: 20px; 
      display: flex; 
      justify-content: space-between; 
      align-items: center;
      border-bottom: 2px solid var(--border);
      padding-bottom: 12px;
    }
    .title { font-size: 24px; font-weight: 900; color: var(--text-main); }
    .subtitle { font-size: 12px; font-weight: 600; color: var(--text-muted); }

    /* 核心：2列网格布局 */
    .grid { 
      display: grid; 
      grid-template-columns: 1fr 1fr; 
      gap: 12px; 
    }

    .day-section {
      background: var(--card-bg);
      border-radius: 14px;
      border: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }

    /* 强调今天：跨过两列 */
    .day-section.is-today {
      grid-column: span 2;
      border: 2px solid var(--accent);
      background: var(--today-bg);
      box-shadow: 0 4px 15px rgba(59, 130, 246, 0.1);
    }
    
    .day-header {
      padding: 8px 12px;
      background: #f1f5f9;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .is-today .day-header { background: var(--accent); color: white; }
    .day-name { font-size: 14px; font-weight: 800; }
    .day-date { font-size: 11px; font-weight: 600; opacity: 0.7; }

    .course-list { padding: 6px; }
    .course-row {
      padding: 8px;
      border-bottom: 1px solid #f1f5f9;
    }
    .course-row:last-child { border-bottom: none; }
    
    .c-time { 
      font-size: 10px; 
      color: var(--accent); 
      font-weight: 800; 
      margin-bottom: 2px;
    }
    .c-name { 
      font-size: 13px; 
      font-weight: 800; 
      color: var(--text-main); 
      line-height: 1.2; 
      margin-bottom: 2px;
    }
    .c-loc { 
      font-size: 10px; 
      color: var(--text-muted); 
      font-weight: 600;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .empty { 
      padding: 12px; 
      color: #cbd5e1; 
      font-size: 11px; 
      font-weight: 700; 
      text-align: center;
    }
    .is-today .empty { color: var(--accent); opacity: 0.5; }
  </style>
</head>
<body>
  <div class="container">
    <div class="title-area">
      <h1 class="title">{{ title }}</h1>
      <p class="subtitle">{{ subtitle.split(' | ')[1] }}</p>
    </div>
    
    <div class="grid">
      {% for day in days %}
        <div class="day-section {{ 'is-today' if day.is_today else '' }}">
          <div class="day-header">
            <span class="day-name">{{ day.label }}{{ ' (今天)' if day.is_today else '' }}</span>
            <span class="day-date">{{ day.date }}</span>
          </div>
          <div class="course-list">
            {% if day.courses|length == 0 %}
              <div class="empty">无课</div>
            {% else %}
              {% for c in day.courses %}
                <div class="course-row">
                  <div class="c-time">{{ c.time_range }}</div>
                  <div class="c-name">{{ c.summary }}</div>
                  <div class="c-loc">📍 {{ c.location if c.location else "待定" }}</div>
                </div>
              {% endfor %}
            {% endif %}
          </div>
        </div>
      {% endfor %}
    </div>
  </div>
</body>
</html>
"""

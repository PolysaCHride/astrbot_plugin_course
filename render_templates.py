DAY_TMPL = r"""
<!doctype html>
<html lang="zh">
<head>
  <meta charset="utf-8" />
  <style>
    :root {
      --bg: #f8fafc;
      --card: #ffffff;
      --border: #e2e8f0;
      --text-main: #1e293b;
      --text-muted: #64748b;
      --accent: #3b82f6;
      --accent-soft: #eff6ff;
    }
    body { 
      margin: 0; 
      background: var(--bg); 
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "PingFang SC", "Microsoft YaHei", sans-serif;
      -webkit-font-smoothing: antialiased;
    }
    .wrap { width: 700px; padding: 40px; margin: 0 auto; box-sizing: border-box; }
    .header { margin-bottom: 32px; border-left: 6px solid var(--accent); padding-left: 20px; }
    .title { color: var(--text-main); font-size: 36px; font-weight: 800; letter-spacing: -0.02em; margin: 0; }
    .sub { margin-top: 8px; color: var(--text-muted); font-size: 18px; font-weight: 500; }
    
    .list { display: grid; gap: 16px; }
    .item { 
      padding: 20px 24px; 
      background: var(--card); 
      border: 1px solid var(--border); 
      border-radius: 16px; 
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
      transition: transform 0.2s;
    }
    .row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
    .name { color: var(--text-main); font-size: 22px; font-weight: 700; }
    .time-tag { 
      background: var(--accent-soft); 
      color: var(--accent); 
      padding: 6px 14px; 
      border-radius: 10px; 
      font-size: 16px; 
      font-weight: 700;
      white-space: nowrap;
    }
    .meta { 
      display: flex; 
      align-items: center; 
      color: var(--text-muted); 
      font-size: 16px; 
      font-weight: 400;
    }
    .meta-icon { margin-right: 8px; opacity: 0.7; }
    
    .empty { 
      padding: 60px; 
      text-align: center;
      color: var(--text-muted); 
      background: var(--card);
      border: 2px dashed var(--border); 
      border-radius: 20px;
      font-size: 20px;
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="header">
      <h1 class="title">{{ title }}</h1>
      <div class="sub">{{ subtitle }}</div>
    </div>
    <div class="list">
      {% if courses|length == 0 %}
        <div class="empty">✨ 今日暂无课程，享受时光吧</div>
      {% else %}
        {% for c in courses %}
          <div class="item">
            <div class="row">
              <div class="name">{{ c.summary }}</div>
              <div class="time-tag">{{ c.time_range }}</div>
            </div>
            <div class="meta">
              <span class="meta-icon">📍</span>
              <span>{{ c.location if c.location else "地点未标注" }}</span>
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
  <style>
    :root {
      --bg: #f1f5f9;
      --text-main: #0f172a;
      --text-muted: #475569;
      --accent: #2563eb;
      --card-bg: #ffffff;
      --border: #e2e8f0;
    }
    body { 
      margin: 0; 
      background: var(--bg); 
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      padding: 40px;
    }
    .container { width: 1200px; margin: 0 auto; }
    .header { text-align: center; margin-bottom: 40px; }
    .title { font-size: 42px; font-weight: 900; color: var(--text-main); margin: 0; letter-spacing: -1px; }
    .sub { font-size: 18px; color: var(--text-muted); margin-top: 10px; font-weight: 500; }
    
    .grid { 
      display: grid; 
      grid-template-columns: repeat(7, 1fr); 
      gap: 12px; 
      align-items: start;
    }
    .day-column { 
      background: rgba(255, 255, 255, 0.5);
      border-radius: 20px;
      padding: 10px;
      min-height: 600px;
    }
    .day-header { 
      text-align: center; 
      padding: 15px 0; 
      margin-bottom: 12px;
    }
    .day-name { font-size: 20px; font-weight: 800; color: var(--text-main); display: block; }
    .day-date { font-size: 14px; color: var(--text-muted); font-weight: 600; margin-top: 4px; display: block; }
    
    .course-list { display: grid; gap: 10px; }
    .course-card { 
      background: var(--card-bg); 
      border: 1px solid var(--border);
      border-radius: 14px; 
      padding: 12px;
      box-shadow: 0 2px 4px rgba(0,0,0,0.02);
    }
    .course-name { 
      font-size: 15px; 
      font-weight: 700; 
      color: var(--text-main); 
      line-height: 1.3;
      margin-bottom: 6px;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }
    .course-time { 
      font-size: 12px; 
      font-weight: 700; 
      color: var(--accent); 
      margin-bottom: 4px;
    }
    .course-loc { 
      font-size: 12px; 
      color: var(--text-muted);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .empty-state {
      text-align: center;
      padding: 20px 0;
      color: #cbd5e1;
      font-size: 13px;
      font-weight: 500;
    }
    .is-today .day-name { color: var(--accent); }
    .is-today { background: #ffffff; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1); border: 2px solid var(--accent); }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1 class="title">{{ title }}</h1>
      <p class="sub">{{ subtitle }}</p>
    </div>
    <div class="grid">
      {% for day in days %}
        <div class="day-column {{ 'is-today' if day.is_today else '' }}">
          <div class="day-header">
            <span class="day-name">{{ day.label }}</span>
            <span class="day-date">{{ day.date }}</span>
          </div>
          <div class="course-list">
            {% if day.courses|length == 0 %}
              <div class="empty-state">No Class</div>
            {% else %}
              {% for c in day.courses %}
                <div class="course-card">
                  <div class="course-time">{{ c.time_range }}</div>
                  <div class="course-name">{{ c.summary }}</div>
                  <div class="course-loc">📍 {{ c.location if c.location else "N/A" }}</div>
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

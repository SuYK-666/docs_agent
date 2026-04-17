const storageKeys = {
  provider: "docs_agent_ui_provider",
  apiKey: "docs_agent_ui_api_key",
  recipients: "docs_agent_ui_recipients",
  emailTypes: "docs_agent_ui_email_types",
  reportLayouts: "docs_agent_ui_report_layouts",
};

const providerDisplayNames = {
  deepseek: "DeepSeek",
  tongyi: "阿里通义系列",
  wenxin: "百度文心系列",
  gaoding: "稿定设计",
  modelwhale: "和鲸ModelWhale",
  jimeng: "即梦",
  doubao: "豆包AI",
  spark: "科大讯飞星火",
  kimi: "Kimi",
  hunyuan: "腾讯混元系列",
  zhipu: "智谱AI",
};

const state = {
  files: [],
  pastedDraftCounter: 0,
  activeInputTab: "upload",
  running: false,
  mode: "preview",
  currentJobId: "",
  pollTimer: null,
  statusEventSource: null,
  lastJobStatus: "",
  reports: [],
  bundleReports: {},
  drafts: [],
  approvalLocked: false,
  recipientEmails: [""],
  activeReportIndex: 0,
  lastRequestPayload: null,
  fileProgressRows: {},
  thinkingBoards: {},
  thinkingBoardOrder: [],
  lastStreamSeq: 0,
};

const defaultEmailFileTypes = ["md", "html", "docx", "ics"];
const JOB_POLL_INTERVAL_MS = 3000;
const JOB_SSE_RETRY_DELAY_MS = 1200;
const FILE_PROGRESS_FALLBACK_ID = "__job__";
const THINKING_RENDER_INTERVAL_MS = 120;
const THINKING_LOCAL_TIMER_INTERVAL_MS = 100;
const THINKING_PANE_MAX_CHARS = 12000;
const THINKING_PANE_TRIM_CHARS = 9000;
const THINKING_AUTO_SCROLL_GAP_PX = 28;
const emailFileTypeLabels = {
  md: "Markdown",
  html: "HTML",
  docx: "Word",
  ics: "ICS",
};

const el = {
  llmProvider: document.getElementById("llmProvider"),
  apiKey: document.getElementById("apiKey"),
  toggleApiKey: document.getElementById("toggleApiKey"),
  emailAttachmentPanel: document.getElementById("emailAttachmentPanel"),
  emailTypeSummary: document.getElementById("emailTypeSummary"),
  mailTypeError: document.getElementById("mailTypeError"),
  emailTypeInputs: Array.from(document.querySelectorAll('input[name="emailFileType"]')),
  reportLayoutInputs: Array.from(document.querySelectorAll("select[data-layout-for]")),
  tabUpload: document.getElementById("tabUpload"),
  tabPaste: document.getElementById("tabPaste"),
  tabCrawl: document.getElementById("tabCrawl"),
  uploadPanel: document.getElementById("uploadPanel"),
  pastePanel: document.getElementById("pastePanel"),
  crawlPanel: document.getElementById("crawlPanel"),
  dropZone: document.getElementById("dropZone"),
  fileInput: document.getElementById("fileInput"),
  fileQueue: document.getElementById("fileQueue"),
  queueCount: document.getElementById("queueCount"),
  pastedText: document.getElementById("pastedText"),
  pastedFileName: document.getElementById("pastedFileName"),
  savePastedTextBtn: document.getElementById("savePastedTextBtn"),
  pasteQueueCount: document.getElementById("pasteQueueCount"),
  crawlUrl: document.getElementById("crawlUrl"),
  crawlCount: document.getElementById("crawlCount"),
  crawlKeyword: document.getElementById("crawlKeyword"),
  modeSwitch: document.getElementById("modeSwitch"),
  startBtn: document.getElementById("startBtn"),
  startGuardHint: document.getElementById("startGuardHint"),
  progressSection: document.getElementById("progressSection"),
  fileProgressList: document.getElementById("fileProgressList"),
  thinkingSection: document.getElementById("thinkingSection"),
  thinkingBoardGrid: document.getElementById("thinkingBoardGrid"),
  resultSection: document.getElementById("resultSection"),
  resultMeta: document.getElementById("resultMeta"),
  bundleTools: document.getElementById("bundleTools"),
  downloadBundleMdBtn: document.getElementById("downloadBundleMdBtn"),
  downloadBundleHtmlBtn: document.getElementById("downloadBundleHtmlBtn"),
  downloadBundleDocxBtn: document.getElementById("downloadBundleDocxBtn"),
  reportTabs: document.getElementById("reportTabs"),
  previewFrame: document.getElementById("previewFrame"),
  approvalSection: document.getElementById("approvalSection"),
  approvalHint: document.getElementById("approvalHint"),
  approvalDocs: document.getElementById("approvalDocs"),
  approvalEmailPanel: document.getElementById("approvalEmailPanel"),
  approvalEmailRows: document.getElementById("approvalEmailRows"),
  approvalEmailError: document.getElementById("approvalEmailError"),
  addRecipientBtn: document.getElementById("addRecipientBtn"),
  removeRecipientBtn: document.getElementById("removeRecipientBtn"),
  approveBtn: document.getElementById("approveBtn"),
  floatingTools: document.getElementById("floatingTools"),
  downloadHtmlBtn: document.getElementById("downloadHtmlBtn"),
  downloadMdBtn: document.getElementById("downloadMdBtn"),
  downloadDocxBtn: document.getElementById("downloadDocxBtn"),
  downloadIcsBtn: document.getElementById("downloadIcsBtn"),
  toastArea: document.getElementById("toastArea"),
  stickyNotice: document.getElementById("stickyNotice"),
  stickyNoticeTitle: document.getElementById("stickyNoticeTitle"),
  stickyNoticeText: document.getElementById("stickyNoticeText"),
  stickyNoticeClose: document.getElementById("stickyNoticeClose"),
};

function getSelectedEmailFileTypes() {
  return el.emailTypeInputs.filter((input) => input.checked).map((input) => input.value);
}

function setEmailFileTypes(values) {
  const selected = new Set(values);
  el.emailTypeInputs.forEach((input) => {
    input.checked = selected.has(input.value);
  });

  el.reportLayoutInputs.forEach((select) => {
    select.addEventListener("change", () => {
      saveLocalMemory();
      validateForm();
    });
  });
}

function getReportLayouts() {
  const defaults = { md: "separate", html: "separate", docx: "bundle" };
  el.reportLayoutInputs.forEach((select) => {
    const fmt = String(select.dataset.layoutFor || "").toLowerCase();
    if (!(fmt in defaults)) {
      return;
    }
    const mode = String(select.value || "").toLowerCase();
    defaults[fmt] = mode === "bundle" ? "bundle" : "separate";
  });
  return defaults;
}

function setReportLayouts(layouts) {
  const normalized = {
    md: String(layouts?.md || "separate").toLowerCase() === "bundle" ? "bundle" : "separate",
    html: String(layouts?.html || "separate").toLowerCase() === "bundle" ? "bundle" : "separate",
    docx: String(layouts?.docx || "bundle").toLowerCase() === "bundle" ? "bundle" : "separate",
  };
  el.reportLayoutInputs.forEach((select) => {
    const fmt = String(select.dataset.layoutFor || "").toLowerCase();
    if (!(fmt in normalized)) {
      return;
    }
    select.value = normalized[fmt];
  });
}

function refreshEmailTypeSelector() {
  const selected = getSelectedEmailFileTypes();
  el.emailTypeInputs.forEach((input) => {
    const option = input.closest(".mail-attachment-option");
    if (!option) {
      return;
    }
    option.classList.toggle("selected", input.checked);

    const fmt = String(input.value || "").toLowerCase();
    const relatedSelect = el.reportLayoutInputs.find((item) => String(item.dataset.layoutFor || "").toLowerCase() === fmt);
    if (relatedSelect) {
      relatedSelect.disabled = !input.checked;
    }
  });

  const names = selected.map((key) => emailFileTypeLabels[key] || key.toUpperCase());
  el.emailTypeSummary.textContent = names.length > 0 ? `已选 ${names.length} 项：${names.join("、")}` : "未选择附件类型";
  el.emailAttachmentPanel.classList.toggle("hidden", state.mode !== "email");
}

function isValidEmail(value) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(value || "").trim());
}

function normalizeRecipientEmails(values) {
  if (!Array.isArray(values)) {
    return [""];
  }
  const normalized = values.map((item) => String(item || ""));
  return normalized.length > 0 ? normalized : [""];
}

function getRecipientValidation() {
  const valid = [];
  const invalid = [];

  state.recipientEmails.forEach((raw) => {
    const email = String(raw || "").trim();
    if (!email) {
      return;
    }
    if (!isValidEmail(email)) {
      invalid.push(email);
      return;
    }
    if (!valid.includes(email)) {
      valid.push(email);
    }
  });

  return { valid, invalid };
}

function renderRecipientRows() {
  if (!el.approvalEmailRows) {
    return;
  }

  if (!Array.isArray(state.recipientEmails) || state.recipientEmails.length === 0) {
    state.recipientEmails = [""];
  }

  const locked = Boolean(state.approvalLocked);
  el.approvalEmailRows.innerHTML = "";

  state.recipientEmails.forEach((value, index) => {
    const row = document.createElement("div");
    row.className = "approval-email-row";
    row.innerHTML = `
      <span class="approval-email-index">${index + 1}</span>
      <input
        type="email"
        placeholder="例如：you@example.com"
        data-recipient-index="${index}"
        value="${String(value || "").replace(/"/g, "&quot;")}"
        ${locked ? "readonly" : ""}
      />
    `;
    el.approvalEmailRows.appendChild(row);
  });

  if (el.addRecipientBtn) {
    el.addRecipientBtn.disabled = locked;
  }
  if (el.removeRecipientBtn) {
    el.removeRecipientBtn.disabled = locked;
  }
}

function validateApprovalRecipients(showError = false) {
  const locked = Boolean(state.approvalLocked);
  
  // 如果是预览模式，直接允许点击（只要没锁定）
  if (state.mode === "preview") {
    const canApprove = !locked;
    if (el.approveBtn) el.approveBtn.disabled = !canApprove;
    if (el.approvalEmailError) el.approvalEmailError.classList.add("hidden");
    return canApprove;
  }

  // 以下是邮件模式的原有逻辑
  const { valid, invalid } = getRecipientValidation();
  const hasValid = valid.length > 0;
  const noInvalid = invalid.length === 0;
  const canApprove = !locked && hasValid && noInvalid;

  if (el.approveBtn) {
    el.approveBtn.disabled = !canApprove;
  }

  if (!el.approvalEmailError) {
    return canApprove;
  }

  if (locked) {
    el.approvalEmailError.classList.add("hidden");
    return canApprove;
  }

  if (!showError && hasValid && noInvalid) {
    el.approvalEmailError.classList.add("hidden");
    return canApprove;
  }

  if (!hasValid) {
    el.approvalEmailError.textContent = "请至少填写一个有效邮箱后再确认。";
  } else if (!noInvalid) {
    el.approvalEmailError.textContent = `存在无效邮箱：${invalid.join("，")}`;
  }
  el.approvalEmailError.classList.remove("hidden");
  return canApprove;
}

function hideApprovalSection() {
  el.approvalSection.classList.add("hidden");
  if (el.approvalHint) {
    el.approvalHint.textContent = "请逐条核对并可直接修改责任人、截止日期；下方填写下发邮箱后再确认执行。";
  }
  el.approvalDocs.innerHTML = "";
  if (el.approvalEmailPanel) {
    el.approvalEmailPanel.classList.add("hidden");
  }
  if (el.approvalEmailError) {
    el.approvalEmailError.classList.add("hidden");
    el.approvalEmailError.textContent = "请至少填写一个有效邮箱后再确认。";
  }
  state.approvalLocked = false;
}

function cloneDrafts(input) {
  if (!Array.isArray(input)) {
    return [];
  }
  return JSON.parse(JSON.stringify(input));
}

function updateDraftTaskField(draftToken, taskId, field, value) {
  const draft = state.drafts.find((item) => item.draft_token === draftToken);
  if (!draft || !draft.draft_json || !Array.isArray(draft.draft_json.tasks)) {
    return;
  }

  const task = draft.draft_json.tasks.find((item) => String(item.task_id || "") === String(taskId || ""));
  if (!task) {
    return;
  }

  task[field] = value;
  if (field === "deadline_display") {
    task.deadline = value;
  }

  if (Array.isArray(draft.tasks)) {
    const rowTask = draft.tasks.find((item) => String(item.task_id || "") === String(taskId || ""));
    if (rowTask) {
      rowTask[field] = value;
      if (field === "deadline_display") {
        rowTask.deadline = value;
      }
    }
  }
}

function renderApprovalSection() {
  // 1. 在函数顶部统一定义一次变量
  const locked = Boolean(state.approvalLocked);

  // 2. 根据状态和模式更新按钮文字
  if (el.approveBtn) {
    if (locked) {
      el.approveBtn.textContent = "已确认（只读）";
    } else {
      // 预览模式显示“完成解析”，邮件模式显示“下发”
      el.approveBtn.textContent = state.mode === "email" ? "确认无误，下发" : "确认无误，完成解析";
    }
  }

  // 3. 更新提示文案
  if (el.approvalHint) {
    el.approvalHint.textContent = locked
      ? "人工审核已完成，以下为确认后的只读留痕记录。"
      : "请逐条核对并可直接修改责任人、截止日期；下方填写下发邮箱后再确认执行。";
  }

  // 4. 清空并检查草稿数据
  el.approvalDocs.innerHTML = "";
  if (!state.drafts.length) {
    hideApprovalSection();
    return;
  }

  // 5. 渲染表格（保持你原来的逻辑）
  state.drafts.forEach((draft) => {
    const card = document.createElement("article");
    card.className = `approval-card ${locked ? "approved" : ""}`;

    const head = document.createElement("div");
    head.className = "approval-card-head";
    head.innerHTML = `
      <strong>${draft.title || draft.doc_id || "待审核文档"}</strong>
      <small>文档ID：${draft.doc_id || "-"} ｜ 待核对任务：${draft.task_count || 0}</small>
    `;

    const tableWrap = document.createElement("div");
    tableWrap.className = "approval-table-wrap";
    const table = document.createElement("table");
    table.className = `approval-table ${locked ? "locked" : ""}`;

    table.innerHTML = `
      <thead>
        <tr>
          <th style="width: 20%">任务ID</th>
          <th style="width: 32%">任务名称</th>
          <th style="width: 24%">责任人（可改）</th>
          <th style="width: 24%">截止日期（可改）</th>
        </tr>
      </thead>
      <tbody></tbody>
    `;

    const tbody = table.querySelector("tbody");
    const tasks = Array.isArray(draft.tasks) ? draft.tasks : [];
    tasks.forEach((task) => {
      const tr = document.createElement("tr");
      const taskId = String(task.task_id || "");
      const taskName = String(task.task_name || "");

      tr.innerHTML = `
        <td class="readonly">${taskId || "-"}</td>
        <td class="readonly">${taskName || "-"}</td>
        <td>
          <input
            type="text"
            value="${String(task.owner || "").replace(/"/g, "&quot;")}"
            data-kind="owner"
            data-draft-token="${draft.draft_token}"
            data-task-id="${taskId}"
            ${locked ? "readonly" : ""}
          />
        </td>
        <td>
          <input
            type="text"
            value="${String(task.deadline_display || task.deadline || "").replace(/"/g, "&quot;")}"
            data-kind="deadline_display"
            data-draft-token="${draft.draft_token}"
            data-task-id="${taskId}"
            ${locked ? "readonly" : ""}
          />
        </td>
      `;
      tbody.appendChild(tr);
    });

    tableWrap.appendChild(table);
    card.appendChild(head);
    card.appendChild(tableWrap);
    el.approvalDocs.appendChild(card);
  });

  // 6. 邮件面板控制
  if (el.approvalEmailPanel) {
    if (state.mode === "email") {
      el.approvalEmailPanel.classList.remove("hidden");
    } else {
      el.approvalEmailPanel.classList.add("hidden");
    }
  }

  renderRecipientRows();
  validateApprovalRecipients(false);

  // 7. 最后：移除 hidden 属性，显示主面板
  el.approvalSection.classList.remove("hidden");
}

function showApprovalDraft(jobData) {
  state.drafts = cloneDrafts(jobData.drafts || []);
  state.approvalLocked = Boolean(jobData.approval_locked);
  const serverRecipients = Array.isArray(jobData.recipient_emails) ? jobData.recipient_emails : null;
  if (serverRecipients && serverRecipients.length > 0) {
    state.recipientEmails = normalizeRecipientEmails(serverRecipients);
  }
  renderApprovalSection();
  if (jobData.reports && jobData.reports.length) {
    showResult(jobData, { suppressToast: true });
  }
}

function loadLocalMemory() {
  const provider = localStorage.getItem(storageKeys.provider) || "deepseek";
  const apiKey = localStorage.getItem(storageKeys.apiKey) || "";
  const recipientsRaw = localStorage.getItem(storageKeys.recipients) || "";
  const rawEmailTypes = localStorage.getItem(storageKeys.emailTypes) || "";
  const rawLayouts = localStorage.getItem(storageKeys.reportLayouts) || "";
  const cachedTypes = rawEmailTypes
    .split(",")
    .map((item) => item.trim().toLowerCase())
    .filter((item) => defaultEmailFileTypes.includes(item));
  const selectedTypes = cachedTypes.length > 0 ? cachedTypes : defaultEmailFileTypes;
  const parsedLayouts = (() => {
    try {
      const parsed = JSON.parse(rawLayouts || "{}");
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch (error) {
      return {};
    }
  })();

  if (el.llmProvider.querySelector(`option[value="${provider}"]`)) {
    el.llmProvider.value = provider;
  }
  el.apiKey.value = apiKey;
  const recipientList = recipientsRaw
    .replace(/\r/g, "\n")
    .split("\n")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
  state.recipientEmails = normalizeRecipientEmails(recipientList.length > 0 ? recipientList : [""]);
  setEmailFileTypes(selectedTypes);
  setReportLayouts(parsedLayouts);
}

function saveLocalMemory() {
  localStorage.setItem(storageKeys.provider, el.llmProvider.value);
  localStorage.setItem(storageKeys.apiKey, el.apiKey.value.trim());
  localStorage.setItem(storageKeys.recipients, state.recipientEmails.map((item) => String(item || "").trim()).join("\n"));
  localStorage.setItem(storageKeys.emailTypes, getSelectedEmailFileTypes().join(","));
  localStorage.setItem(storageKeys.reportLayouts, JSON.stringify(getReportLayouts()));
}

function refreshProviderHint() {
  const provider = el.llmProvider.value;
  const providerName = providerDisplayNames[provider] || "当前模型";
  el.apiKey.placeholder = `请输入 ${providerName} API Key`;
}

function bytesToSize(bytes) {
  const units = ["B", "KB", "MB", "GB"];
  let size = bytes;
  let unit = units[0];
  for (let i = 0; i < units.length; i += 1) {
    unit = units[i];
    if (size < 1024 || i === units.length - 1) {
      break;
    }
    size /= 1024;
  }
  return `${size.toFixed(size > 10 ? 0 : 1)} ${unit}`;
}

function escapeHtml(text) {
  return String(text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function buildDefaultPastedFileName() {
  const now = new Date();
  const pad = (value) => String(value).padStart(2, "0");
  const stamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
  state.pastedDraftCounter += 1;
  return `paste_notice_${stamp}_${String(state.pastedDraftCounter).padStart(2, "0")}.txt`;
}

function normalizePastedFileName(rawName) {
  const normalized = String(rawName || "")
    .trim()
    .replace(/[\\/:*?"<>|]+/g, "_")
    .replace(/\s+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "");

  if (!normalized) {
    return buildDefaultPastedFileName();
  }

  return normalized.toLowerCase().endsWith(".txt") ? normalized : `${normalized}.txt`;
}

function normalizeFileList(fileList, source = "upload") {
  const incoming = Array.from(fileList || []);
  incoming.forEach((file) => {
    const id = `${file.name}_${file.size}_${file.lastModified}_${Math.random().toString(16).slice(2, 8)}`;
    state.files.push({ id, file, source });
  });
  renderQueue();
}

function addPastedTextToQueue(options = {}) {
  const { silent = false, clearInput = true } = options;
  const text = el.pastedText.value.trim();
  if (!text) {
    if (!silent) {
      showToast("请先粘贴正文，再保存到队列。", "error");
    }
    return false;
  }

  const rawName = el.pastedFileName ? el.pastedFileName.value : "";
  const txtFileName = normalizePastedFileName(rawName);
  const file = new File([`${text}\n`], txtFileName, {
    type: "text/plain;charset=utf-8",
    lastModified: Date.now(),
  });

  normalizeFileList([file], "paste_text");

  if (clearInput) {
    el.pastedText.value = "";
    if (el.pastedFileName) {
      el.pastedFileName.value = "";
    }
  }

  if (!silent) {
    showToast(`已加入队列：${txtFileName}`, "info");
  }

  return true;
}

function addClipboardFilesToQueue(clipboardFiles) {
  const files = Array.from(clipboardFiles || []);
  if (files.length === 0) {
    return;
  }
  normalizeFileList(files, "clipboard_file");
  showToast(`已从剪贴板加入 ${files.length} 个文件。`, "info");
}

function renderQueue() {
  el.fileQueue.innerHTML = "";

  if (state.files.length === 0) {
    const li = document.createElement("li");
    li.className = "queue-item";
    li.innerHTML = '<div class="queue-meta"><strong>暂无文件</strong><small>可拖拽或点击上方区域添加。</small></div>';
    el.fileQueue.appendChild(li);
  } else {
    state.files.forEach((item) => {
      const li = document.createElement("li");
      li.className = "queue-item";
      const sourceLabel =
        item.source === "paste_text"
          ? "粘贴文本"
          : item.source === "clipboard_file"
            ? "剪贴板文件"
            : "上传文件";
      li.innerHTML = `
        <div class="queue-meta">
          <strong>${escapeHtml(item.file.name)}</strong>
          <small>${sourceLabel} · ${bytesToSize(item.file.size)}</small>
        </div>
        <button class="remove-btn" data-id="${item.id}" type="button" title="移除文件">🗑</button>
      `;
      el.fileQueue.appendChild(li);
    });
  }

  el.queueCount.textContent = `${state.files.length} 份`;
  if (el.pasteQueueCount) {
    el.pasteQueueCount.textContent = String(state.files.length);
  }
  validateForm();
}

function showToast(message, type = "info", withRetry = false, retryHandler = null) {
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;

  const row = document.createElement("div");
  row.className = "row";
  const text = document.createElement("span");
  text.textContent = message;
  row.appendChild(text);

  if (withRetry && typeof retryHandler === "function") {
    const retryBtn = document.createElement("button");
    retryBtn.className = "retry";
    retryBtn.type = "button";
    retryBtn.textContent = "一键重试";
    retryBtn.addEventListener("click", () => {
      toast.remove();
      retryHandler();
    });
    row.appendChild(retryBtn);
  }

  toast.appendChild(row);
  el.toastArea.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    setTimeout(() => toast.remove(), 280);
  }, withRetry ? 9000 : 3600);
}

function hideStickyNotice() {
  if (!el.stickyNotice) {
    return;
  }
  el.stickyNotice.classList.add("hidden");
}

function showStickyNotice(title, message) {
  if (!el.stickyNotice || !el.stickyNoticeTitle || !el.stickyNoticeText) {
    return;
  }
  el.stickyNoticeTitle.textContent = title;
  el.stickyNoticeText.textContent = message;
  el.stickyNotice.classList.remove("hidden");
}

function setMode(mode) {
  state.mode = mode;
  Array.from(document.querySelectorAll(".mode-option")).forEach((option) => {
    option.classList.toggle("active", option.dataset.mode === mode);
  });
  refreshEmailTypeSelector();
  validateForm();
}

function clampPercent(value, fallback = 0) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return Math.max(0, Math.min(100, Math.round(fallback)));
  }
  return Math.max(0, Math.min(100, Math.round(parsed)));
}

function normalizeCrawlCount(value) {
  const count = Number.parseInt(String(value || ""), 10);
  if (!Number.isFinite(count)) {
    return 5;
  }
  return Math.max(1, Math.min(20, count));
}

function getHasInputByActiveTab() {
  if (state.activeInputTab === "crawl") {
    const crawlUrl = el.crawlUrl ? el.crawlUrl.value.trim() : "";
    return crawlUrl.length > 0 && normalizeCrawlCount(el.crawlCount ? el.crawlCount.value : "") > 0;
  }

  if (state.activeInputTab === "paste") {
    return state.files.length > 0 || el.pastedText.value.trim().length > 0;
  }

  return state.files.length > 0;
}

function validateForm() {
  const hasApiKey = el.apiKey.value.trim().length > 0;
  const hasInput = getHasInputByActiveTab();
  const requiresEmail = state.mode === "email";
  const hasEmailTypes = getSelectedEmailFileTypes().length > 0;
  const blockers = [];

  if (state.running) {
    blockers.push("任务正在执行中，请等待当前任务完成");
  }
  if (!hasApiKey) {
    blockers.push("请先填写模型 API Key");
  }
  if (!hasInput) {
    if (state.activeInputTab === "crawl") {
      blockers.push("请填写抓取入口 URL");
    } else if (state.activeInputTab === "paste") {
      blockers.push("请先粘贴文本或加入待处理文件");
    } else {
      blockers.push("请先上传至少一份待处理文件");
    }
  }
  if (requiresEmail && !hasEmailTypes) {
    blockers.push("邮件模式下至少选择一种附件类型");
  }

  const canRun = !state.running && hasApiKey && hasInput && (!requiresEmail || hasEmailTypes);
  el.startBtn.disabled = !canRun;
  el.startBtn.title = canRun ? "开始智能解析" : blockers.join("；");

  if (el.startGuardHint) {
    if (canRun) {
      el.startGuardHint.textContent = "";
      el.startGuardHint.classList.add("hidden");
    } else {
      el.startGuardHint.textContent = blockers.join("；");
      el.startGuardHint.classList.remove("hidden");
    }
  }

  if (requiresEmail && !hasEmailTypes) {
    el.mailTypeError.classList.remove("hidden");
  } else {
    el.mailTypeError.classList.add("hidden");
  }
}

function setBusy(busy) {
  state.running = busy;
  const spinner = el.startBtn.querySelector(".spinner");
  const label = el.startBtn.querySelector(".label");
  if (spinner) {
    spinner.classList.toggle("hidden", !busy);
  }
  if (label) {
    label.textContent = busy ? "智能解析进行中..." : "开始智能解析";
  }
  validateForm();
}

function getProgressKey(rawId) {
  const normalized = String(rawId || "").trim();
  return normalized || FILE_PROGRESS_FALLBACK_ID;
}

function ensureFileProgressRow(fileId, fileName) {
  if (!el.fileProgressList) {
    return null;
  }

  const key = getProgressKey(fileId);
  const existing = state.fileProgressRows[key];
  if (existing) {
    const titleNode = existing.querySelector(".file-progress-name");
    if (titleNode && fileName) {
      titleNode.textContent = fileName;
    }
    return existing;
  }

  const row = document.createElement("article");
  row.className = "file-progress-item pending";
  row.dataset.fileId = key;
  row.dataset.percent = "0";
  row.innerHTML = `
    <div class="file-progress-head">
      <strong class="file-progress-name">${escapeHtml(fileName || key)}</strong>
      <span class="file-progress-percent">0%</span>
    </div>
    <div class="file-progress-track">
      <div class="file-progress-fill" style="width: 0%"></div>
    </div>
    <p class="file-progress-detail">等待处理</p>
  `;

  state.fileProgressRows[key] = row;
  el.fileProgressList.appendChild(row);
  return row;
}

function updateFileProgress(fileId, options = {}) {
  const key = getProgressKey(fileId);
  const fileName = String(options.fileName || options.file_name || "").trim();
  const row = ensureFileProgressRow(key, fileName || (key === FILE_PROGRESS_FALLBACK_ID ? "总体任务" : key));
  if (!row) {
    return;
  }

  const percentNode = row.querySelector(".file-progress-percent");
  const fillNode = row.querySelector(".file-progress-fill");
  const detailNode = row.querySelector(".file-progress-detail");
  const titleNode = row.querySelector(".file-progress-name");

  const previous = Number(row.dataset.percent || 0);
  const nextPercent =
    options.percent === undefined || options.percent === null ? clampPercent(previous, 0) : clampPercent(options.percent, previous);

  row.dataset.percent = String(nextPercent);
  if (percentNode) {
    percentNode.textContent = `${nextPercent}%`;
  }
  if (fillNode) {
    fillNode.style.width = `${nextPercent}%`;
  }
  if (titleNode && fileName) {
    titleNode.textContent = fileName;
  }

  const detail = String(options.detail || options.stepDetail || "").trim();
  if (detail && detailNode) {
    detailNode.textContent = detail;
  }

  const status = String(options.status || "").toLowerCase();
  row.classList.remove("pending", "active", "done", "failed");
  if (status === "failed") {
    row.classList.add("failed");
  } else if (status === "success" || nextPercent >= 100) {
    row.classList.add("done");
  } else if (status === "running" || status === "pending_approval" || nextPercent > 0) {
    row.classList.add("active");
  } else {
    row.classList.add("pending");
  }

  if (!options.skipOverallSync && key !== FILE_PROGRESS_FALLBACK_ID) {
    refreshOverallProgressRow();
  }
}

function getFileProgressPercent(fileId) {
  const key = getProgressKey(fileId);
  const row = state.fileProgressRows[key];
  if (!row) {
    return 0;
  }
  const parsed = Number(row.dataset.percent || 0);
  return Number.isFinite(parsed) ? Math.max(0, Math.min(100, parsed)) : 0;
}

function getProgressSummary() {
  const entries = Object.entries(state.fileProgressRows || {}).filter(([key]) => key !== FILE_PROGRESS_FALLBACK_ID);
  if (entries.length === 0) {
    return null;
  }

  let done = 0;
  let active = 0;
  let failed = 0;
  let pending = 0;
  let percentSum = 0;

  entries.forEach(([, row]) => {
    const percent = Number(row?.dataset?.percent || 0);
    percentSum += Number.isFinite(percent) ? Math.max(0, Math.min(100, percent)) : 0;
    if (row.classList.contains("failed")) {
      failed += 1;
      return;
    }
    if (row.classList.contains("done")) {
      done += 1;
      return;
    }
    if (row.classList.contains("active")) {
      active += 1;
      return;
    }
    pending += 1;
  });

  const total = entries.length;
  const avgPercent = Math.round(percentSum / total);
  return { total, done, active, failed, pending, avgPercent };
}

function refreshOverallProgressRow(detailOverride = "") {
  const summary = getProgressSummary();
  if (!summary) {
    return;
  }

  const status =
    summary.failed > 0
      ? "running"
      : summary.done >= summary.total
        ? "success"
        : summary.active > 0
          ? "running"
          : "pending";

  const autoDetail =
    detailOverride ||
    (summary.done >= summary.total
      ? `全部完成（${summary.total}/${summary.total}）`
      : `已完成 ${summary.done}/${summary.total}，运行中 ${summary.active}，待处理 ${summary.pending}`);

  updateFileProgress(
    FILE_PROGRESS_FALLBACK_ID,
    {
      fileName: "总体任务",
      percent: summary.avgPercent,
      detail: autoDetail,
      status,
      skipOverallSync: true,
    },
  );
}

function resetFileProgressRows(seedItems = []) {
  state.fileProgressRows = {};
  if (!el.fileProgressList) {
    return;
  }
  el.fileProgressList.innerHTML = "";

  if (!Array.isArray(seedItems) || seedItems.length === 0) {
    ensureFileProgressRow(FILE_PROGRESS_FALLBACK_ID, "总体任务");
    return;
  }

  seedItems.forEach((item, index) => {
    const key = getProgressKey(item.id || `file_${index + 1}`);
    const displayName = String(item.name || item.fileName || `任务 ${index + 1}`).trim();
    ensureFileProgressRow(key, displayName || `任务 ${index + 1}`);
  });
}

function buildFileProgressSeeds() {
  if (state.activeInputTab === "crawl") {
    return [
      {
        id: "__crawl__",
        name: "网页抓取阶段",
      },
    ];
  }

  if (state.files.length > 0) {
    return state.files.map((item, index) => ({
      id: item.file && item.file.name ? item.file.name : item.id || `file_${index + 1}`,
      name: item.file && item.file.name ? item.file.name : `任务 ${index + 1}`,
    }));
  }

  const rawPaste = el.pastedText.value.trim();
  if (rawPaste) {
    return [
      {
        id: "paste_1",
        name: normalizePastedFileName(el.pastedFileName ? el.pastedFileName.value : "") || "粘贴文本",
      },
    ];
  }

  return [{ id: FILE_PROGRESS_FALLBACK_ID, name: "总体任务" }];
}

function updateProgressFromJobPayload(data) {
  const fileId = String(data.file_id || "").trim();
  const fileName = String(data.file_name || "").trim();
  const hasFilePercent = Number.isFinite(Number(data.file_percent));
  const stepDetail = String(data.step_detail || "").trim();

  if (fileId || hasFilePercent || stepDetail) {
    updateFileProgress(fileId || FILE_PROGRESS_FALLBACK_ID, {
      fileName,
      percent: hasFilePercent ? Number(data.file_percent) : undefined,
      detail: stepDetail || data.step_text || "处理中",
      status: data.status,
    });
    return;
  }

  updateFileProgress(FILE_PROGRESS_FALLBACK_ID, {
    fileName: "总体任务",
    percent: Number(data.progress || 0),
    detail: data.step_text || "处理中",
    status: data.status,
  });
}

function nowClockText() {
  const now = new Date();
  const pad = (value) => String(value).padStart(2, "0");
  return `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
}

function normalizeThinkingAgent(rawAgent, rawNode) {
  const merged = String(rawAgent || rawNode || "").trim().toLowerCase();
  if (merged.includes("reader")) {
    return "reader";
  }
  if (merged.includes("reviewer")) {
    return "reviewer";
  }
  if (merged.includes("dispatcher")) {
    return "dispatcher";
  }
  return "system";
}

function formatThinkingAgentLabel(agent) {
  if (agent === "reader") {
    return "Reader";
  }
  if (agent === "reviewer") {
    return "Reviewer";
  }
  if (agent === "dispatcher") {
    return "Dispatcher";
  }
  return "System";
}

function normalizeThinkingDocKey(rawDocId, rawFileName, rawFileId) {
  const candidate = String(rawDocId || rawFileName || rawFileId || "").trim();
  return candidate || "__job__";
}

function buildThinkingDomId(docKey) {
  const normalized = encodeURIComponent(String(docKey || "__job__"))
    .replace(/%/g, "_")
    .replace(/[^a-zA-Z0-9_-]/g, "_");
  return `box-${normalized}`;
}

function buildThinkingPaneDomId(docKey, agent) {
  const normalized = encodeURIComponent(String(docKey || "__job__"))
    .replace(/%/g, "_")
    .replace(/[^a-zA-Z0-9_-]/g, "_");
  return `${agent}-${normalized}`;
}

function formatElapsedClock(totalMs) {
  const ms = Math.max(0, Number(totalMs || 0));
  const minutes = Math.floor(ms / 60000);
  const seconds = Math.floor((ms % 60000) / 1000);
  const centiseconds = Math.floor((ms % 1000) / 10);
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}.${String(centiseconds).padStart(2, "0")}`;
}

function sanitizeIncomingStreamText(rawText) {
  const text = String(rawText || "")
    .replace(/\r/g, "")
    .replace(/\u0000/g, "");
  if (!text.trim()) {
    return "";
  }
  // Keep original wording as much as possible; only drop pure structural noise.
  if (/^[\s{}\[\]",:]+$/.test(text)) {
    return "";
  }
  return text;
}

function estimateTokenDelta(text) {
  const normalized = String(text || "").trim();
  if (!normalized) {
    return 0;
  }
  return Math.max(1, Math.ceil(normalized.length / 2));
}

function getThinkingBoard(docKey) {
  const key = normalizeThinkingDocKey(docKey);
  return state.thinkingBoards[key] || null;
}

function getPaneLabel(stateKey) {
  if (stateKey === "active") {
    return "运行中";
  }
  if (stateKey === "done") {
    return "完成";
  }
  if (stateKey === "error") {
    return "异常";
  }
  return "等待";
}

function setThinkingBoardStatus(board, statusKey, labelText) {
  if (!board || !board.statusEl || !board.statusTextEl) {
    return;
  }
  const normalized = String(statusKey || "waiting").trim().toLowerCase();
  board.statusEl.className = `thinking-board-status ${normalized}`;
  board.statusTextEl.textContent = String(labelText || "等待中");
}

function setPaneStatus(board, agent, stateKey, statusText = "") {
  if (!board || !board.panes || !board.panes[agent]) {
    return;
  }
  const pane = board.panes[agent];
  const normalized = String(stateKey || "waiting").trim().toLowerCase();
  pane.state = normalized;
  if (pane.wrapEl) {
    pane.wrapEl.className = `thinking-agent-pane ${normalized}`;
  }
  if (pane.statusEl) {
    pane.statusEl.textContent = String(statusText || getPaneLabel(normalized));
  }
}

function updateBoardElapsedLabel(board) {
  if (!board || !board.elapsedEl) {
    return;
  }
  const runningMs = board.timerStartedAt > 0 ? Date.now() - board.timerStartedAt : 0;
  board.elapsedEl.textContent = formatElapsedClock(board.elapsedAccumMs + runningMs);
}

function startBoardElapsedTimer(board) {
  if (!board) {
    return;
  }
  if (board.elapsedTimerId) {
    return;
  }
  board.timerStartedAt = Date.now();
  updateBoardElapsedLabel(board);
  board.elapsedTimerId = setInterval(() => {
    updateBoardElapsedLabel(board);
  }, THINKING_LOCAL_TIMER_INTERVAL_MS);
}

function stopBoardElapsedTimer(board) {
  if (!board) {
    return;
  }
  if (board.elapsedTimerId) {
    clearInterval(board.elapsedTimerId);
    board.elapsedTimerId = null;
  }
  if (board.timerStartedAt > 0) {
    board.elapsedAccumMs += Date.now() - board.timerStartedAt;
    board.timerStartedAt = 0;
  }
  updateBoardElapsedLabel(board);
}

function setBoardTokenCount(board, nextValue) {
  if (!board || !board.tokenEl) {
    return;
  }
  const parsed = Number(nextValue);
  if (!Number.isFinite(parsed)) {
    return;
  }
  board.tokenCount = Math.max(0, Math.round(parsed));
  board.tokenEl.textContent = String(board.tokenCount);
}

function isCrawlDocKey(docKey) {
  const key = String(docKey || "").trim();
  return key === "__crawl__" || key === "网页抓取阶段";
}

function ensureThinkingBoard(docKey, displayTitle = "", options = {}) {
  const key = normalizeThinkingDocKey(docKey);
  const wantsCrawlOnly = Boolean(options?.crawlOnly) || isCrawlDocKey(key);
  const existing = getThinkingBoard(key);
  const nextTitle = String(displayTitle || key).trim() || key;
  if (existing) {
    if (existing.titleEl) {
      existing.titleEl.textContent = nextTitle;
    }
    if (wantsCrawlOnly) {
      existing.isCrawlBoard = true;
      if (existing.element) {
        existing.element.classList.add("crawl-board");
      }
    }
    return existing;
  }

  if (!el.thinkingBoardGrid) {
    return null;
  }

  const article = document.createElement("article");
  article.className = `thinking-board${wantsCrawlOnly ? " crawl-board" : ""}`;
  article.dataset.docKey = key;
  const containerId = buildThinkingDomId(key);
  const readerId = buildThinkingPaneDomId(key, "reader");
  const reviewerId = buildThinkingPaneDomId(key, "reviewer");
  const dispatcherId = buildThinkingPaneDomId(key, "dispatcher");
  const readerLabel = wantsCrawlOnly ? "[Crawler 抓取]" : "[Reader 抽取]";
  const subtitle = wantsCrawlOnly ? "crawl_stage: 网页抓取阶段" : `doc_id: ${escapeHtml(key)}`;
  const reviewerPaneHtml = wantsCrawlOnly
    ? ""
    : `
      <section id="${reviewerId}" class="thinking-agent-pane waiting" data-agent="reviewer">
        <header class="thinking-pane-head">
          <strong>[Reviewer 复核]</strong>
          <span class="pane-status">等待</span>
        </header>
        <div class="thinking-stream" role="log" aria-live="polite"></div>
      </section>
    `;
  const dispatcherPaneHtml = wantsCrawlOnly
    ? ""
    : `
      <section id="${dispatcherId}" class="thinking-agent-pane waiting" data-agent="dispatcher">
        <header class="thinking-pane-head">
          <strong>[Dispatcher 分发]</strong>
          <span class="pane-status">等待</span>
        </header>
        <div class="thinking-stream" role="log" aria-live="polite"></div>
      </section>
    `;

  article.innerHTML = `
    <div class="thinking-board-head">
      <div class="thinking-file-meta">
        <strong class="thinking-board-title">${escapeHtml(nextTitle)}</strong>
        <span class="thinking-board-subtitle">${subtitle}</span>
      </div>
      <span class="thinking-counter">耗时 <em class="thinking-elapsed">00:00.00</em></span>
      <span class="thinking-counter">Token <em class="thinking-tokens">0</em></span>
      <div class="thinking-board-status waiting">
        <span class="status-dot"></span>
        <span class="status-text">等待中</span>
      </div>
    </div>
    <div id="${containerId}" class="thinking-file-body">
      <section id="${readerId}" class="thinking-agent-pane waiting" data-agent="reader">
        <header class="thinking-pane-head">
          <strong>${readerLabel}</strong>
          <span class="pane-status">等待</span>
        </header>
        <div class="thinking-stream" role="log" aria-live="polite"></div>
      </section>
      ${reviewerPaneHtml}
      ${dispatcherPaneHtml}
    </div>
  `;

  el.thinkingBoardGrid.appendChild(article);

  const board = {
    key,
    element: article,
    titleEl: article.querySelector(".thinking-board-title"),
    statusEl: article.querySelector(".thinking-board-status"),
    statusTextEl: article.querySelector(".status-text"),
    elapsedEl: article.querySelector(".thinking-elapsed"),
    tokenEl: article.querySelector(".thinking-tokens"),
    elapsedAccumMs: 0,
    timerStartedAt: 0,
    elapsedTimerId: null,
    tokenCount: 0,
    isCrawlBoard: wantsCrawlOnly,
    crawlFinished: false,
    panes: {
      reader: {
        agent: "reader",
        wrapEl: article.querySelector(`#${readerId}`),
        statusEl: article.querySelector(`#${readerId} .pane-status`),
        streamEl: article.querySelector(`#${readerId} .thinking-stream`),
        outputEl: null,
        buffer: "",
        renderTimerId: null,
        content: "",
        state: "waiting",
      },
      ...(wantsCrawlOnly
        ? {}
        : {
            reviewer: {
              agent: "reviewer",
              wrapEl: article.querySelector(`#${reviewerId}`),
              statusEl: article.querySelector(`#${reviewerId} .pane-status`),
              streamEl: article.querySelector(`#${reviewerId} .thinking-stream`),
              outputEl: null,
              buffer: "",
              renderTimerId: null,
              content: "",
              state: "waiting",
              lastScoreText: "",
              scoreTimeline: [],
              scoreByAttempt: {},
            },
            dispatcher: {
              agent: "dispatcher",
              wrapEl: article.querySelector(`#${dispatcherId}`),
              statusEl: article.querySelector(`#${dispatcherId} .pane-status`),
              streamEl: article.querySelector(`#${dispatcherId} .thinking-stream`),
              outputEl: null,
              buffer: "",
              renderTimerId: null,
              content: "",
              state: "waiting",
            },
          }),
    },
  };

  updateBoardElapsedLabel(board);
  setThinkingBoardStatus(board, "waiting", "等待中");
  setPaneStatus(board, "reader", "waiting", "等待");
  setPaneStatus(board, "reviewer", "waiting", "等待");
  setPaneStatus(board, "dispatcher", "waiting", "等待");

  state.thinkingBoards[key] = board;
  state.thinkingBoardOrder.push(key);
  return board;
}

function ensureFallbackThinkingBoard() {
  const existing = getThinkingBoard("__job__");
  if (existing) {
    return existing;
  }
  return ensureThinkingBoard("__job__", "总体任务");
}

function clearThinkingTimers() {
  Object.values(state.thinkingBoards || {}).forEach((board) => {
    if (!board) {
      return;
    }
    stopBoardElapsedTimer(board);
    ["reader", "reviewer", "dispatcher"].forEach((agent) => {
      const pane = board.panes?.[agent];
      if (!pane) {
        return;
      }
      if (pane.renderTimerId) {
        clearInterval(pane.renderTimerId);
        pane.renderTimerId = null;
      }
    });
  });
}

function resetThinkingEngine(options = {}) {
  const { hide = true, seedItems = [] } = options;
  clearThinkingTimers();

  if (el.thinkingSection) {
    el.thinkingSection.classList.toggle("hidden", hide);
  }

  state.thinkingBoards = {};
  state.thinkingBoardOrder = [];
  if (el.thinkingBoardGrid) {
    el.thinkingBoardGrid.innerHTML = "";
  }

  if (Array.isArray(seedItems)) {
    seedItems.forEach((item) => {
      const key = normalizeThinkingDocKey(item?.id, item?.name, item?.docId);
      const title = String(item?.name || key).trim() || key;
      ensureThinkingBoard(key, title, { crawlOnly: String(item?.mode || "").toLowerCase() === "crawl" });
    });
  }
}

function shouldPinThinkingPane(streamEl) {
  if (!streamEl) {
    return true;
  }
  const remaining = streamEl.scrollHeight - streamEl.scrollTop - streamEl.clientHeight;
  return remaining <= THINKING_AUTO_SCROLL_GAP_PX;
}

function flushPaneBuffer(board, agent) {
  if (!board || !board.panes || !board.panes[agent]) {
    return;
  }
  const pane = board.panes[agent];
  if (!pane.streamEl) {
    return;
  }

  if (!pane.buffer) {
    if (pane.renderTimerId) {
      clearInterval(pane.renderTimerId);
      pane.renderTimerId = null;
    }
    return;
  }

  if (!pane.outputEl) {
    const output = document.createElement("p");
    output.className = `thinking-token-line agent-${agent}`;
    output.textContent = "";
    pane.streamEl.appendChild(output);
    pane.outputEl = output;
  }

  pane.content += pane.buffer;
  pane.buffer = "";
  const shouldPin = shouldPinThinkingPane(pane.streamEl);

  if (pane.content.length > THINKING_PANE_MAX_CHARS) {
    pane.content = pane.content.slice(-THINKING_PANE_TRIM_CHARS);
  }

  pane.outputEl.textContent = pane.content;
  if (shouldPin) {
    pane.streamEl.scrollTop = pane.streamEl.scrollHeight;
  }

  if (pane.renderTimerId) {
    clearInterval(pane.renderTimerId);
    pane.renderTimerId = null;
  }
}

function appendPaneMeta(board, agent, message, kind = "status", withDivider = false) {
  if (!board || !board.panes || !board.panes[agent]) {
    return;
  }
  const pane = board.panes[agent];
  if (!pane.streamEl) {
    return;
  }
  const shouldPin = shouldPinThinkingPane(pane.streamEl);

  flushPaneBuffer(board, agent);
  pane.outputEl = null;

  const line = document.createElement("div");
  line.className = `thinking-meta-line${kind === "done" ? " done" : ""}${kind === "error" ? " error" : ""}`;
  line.textContent = String(message || "");
  pane.streamEl.appendChild(line);

  if (withDivider) {
    const divider = document.createElement("div");
    divider.className = "thinking-divider";
    pane.streamEl.appendChild(divider);
  }

  if (shouldPin) {
    pane.streamEl.scrollTop = pane.streamEl.scrollHeight;
  }
}

function enqueuePaneToken(board, agent, text) {
  if (!board || !board.panes || !board.panes[agent]) {
    return;
  }
  const pane = board.panes[agent];
  const compacted = sanitizeIncomingStreamText(text);
  if (!compacted) {
    return;
  }
  pane.buffer += compacted;
  if (!pane.renderTimerId) {
    pane.renderTimerId = setInterval(() => {
      flushPaneBuffer(board, agent);
    }, THINKING_RENDER_INTERVAL_MS);
  }
}

function activateBoardStage(board, agent) {
  if (!board) {
    return;
  }
  ["reader", "reviewer", "dispatcher"].forEach((name) => {
    const pane = board.panes?.[name];
    if (!pane) {
      return;
    }
    if (name === agent) {
      setPaneStatus(board, name, "active", "运行中");
      return;
    }
    if (pane.state === "done" || pane.state === "error") {
      return;
    }
    setPaneStatus(board, name, "waiting", "等待");
  });
}

function broadcastThinkingMeta(message, kind = "status") {
  const text = String(message || "").trim();
  if (!text) {
    return;
  }
  if (state.thinkingBoardOrder.length === 0) {
    ensureFallbackThinkingBoard();
  }
  state.thinkingBoardOrder.forEach((docKey) => {
    const board = getThinkingBoard(docKey);
    if (!board) {
      return;
    }
    if (board.isCrawlBoard) {
      return;
    }
    appendPaneMeta(board, "reader", `[${nowClockText()}] ${text}`, kind, false);
  });
}

function setAllThinkingBoardStatus(statusKey, labelText) {
  if (state.thinkingBoardOrder.length === 0) {
    ensureFallbackThinkingBoard();
  }
  state.thinkingBoardOrder.forEach((docKey) => {
    const board = getThinkingBoard(docKey);
    if (!board) {
      return;
    }
    if (board.isCrawlBoard) {
      return;
    }
    setThinkingBoardStatus(board, statusKey, labelText);
    if (statusKey === "done" || statusKey === "error" || statusKey === "pending-approval") {
      stopBoardElapsedTimer(board);
    }
  });
}

function getAgentRunningStatus(agent) {
  if (agent === "reader") {
    return { key: "extracting", label: "抽取中" };
  }
  if (agent === "reviewer") {
    return { key: "reviewing", label: "复核中" };
  }
  if (agent === "dispatcher") {
    return { key: "dispatching", label: "下发中" };
  }
  return { key: "waiting", label: "处理中" };
}

function resolveProgressFileId(docKey, fileName, rawData) {
  const candidate = String(fileName || rawData?.file_id || rawData?.doc_id || docKey || "").trim();
  return candidate || FILE_PROGRESS_FALLBACK_ID;
}

function setProgressAtLeast(fileId, fileName, minPercent, detail, status = "running") {
  const current = getFileProgressPercent(fileId);
  const target = Math.max(current, clampPercent(minPercent, current));
  updateFileProgress(fileId, {
    fileName: fileName || fileId,
    percent: target,
    detail,
    status,
  });
}

function bumpProgressWithinCap(fileId, fileName, capPercent, step, detail, status = "running") {
  const current = getFileProgressPercent(fileId);
  const cap = clampPercent(capPercent, current);
  const delta = Math.max(1, Number(step) || 1);
  const target = Math.min(cap, current + delta);
  if (target <= current) {
    return;
  }
  updateFileProgress(fileId, {
    fileName: fileName || fileId,
    percent: target,
    detail,
    status,
  });
}

function upsertReviewerScoreTimeline(pane, attempt, score) {
  if (!pane) {
    return "";
  }
  if (!pane.scoreByAttempt || typeof pane.scoreByAttempt !== "object") {
    pane.scoreByAttempt = {};
  }

  const round = Math.max(1, Math.round(Number(attempt) || 1));
  const normalizedScore = Math.max(0, Math.round(Number(score) || 0));
  const label = `第${round}轮${normalizedScore}分`;
  pane.scoreByAttempt[String(round)] = label;

  const ordered = Object.entries(pane.scoreByAttempt)
    .map(([key, value]) => ({ round: Number(key), text: String(value || "") }))
    .filter((item) => Number.isFinite(item.round) && item.text)
    .sort((a, b) => a.round - b.round)
    .map((item) => item.text);

  pane.scoreTimeline = ordered;
  pane.lastScoreText = ordered.length > 0 ? ordered[ordered.length - 1] : "";
  return ordered.join(" | ");
}

function getReviewerScoreSummary(pane) {
  if (!pane) {
    return "";
  }
  if (Array.isArray(pane.scoreTimeline) && pane.scoreTimeline.length > 0) {
    return pane.scoreTimeline.join(" | ");
  }
  return String(pane.lastScoreText || "");
}

function buildThinkingSeedItems() {
  return buildFileProgressSeeds().map((item, index) => {
    const id = normalizeThinkingDocKey(item?.id, item?.name, `seed_${index + 1}`);
    const name = String(item?.name || id).trim() || id;
    return { id, name, mode: id === "__crawl__" ? "crawl" : "doc" };
  });
}

function applyStreamUpdate(data) {
  const eventType = String(data?.event || "token").trim().toLowerCase() || "token";
  const agent = normalizeThinkingAgent(data?.agent, data?.node);
  let docKey = normalizeThinkingDocKey(data?.file_name, data?.doc_id, data?.file_id);
  let fileName = String(data?.file_name || "").trim();
  let boardTitle = fileName || String(data?.doc_id || docKey);
  const boardOptions = { crawlOnly: false };

  if (eventType === "crawler_progress" || eventType === "crawler_done") {
    docKey = "__crawl__";
    fileName = "网页抓取阶段";
    boardTitle = "网页抓取阶段";
    boardOptions.crawlOnly = true;
  } else if (eventType === "crawl_file_found") {
    const discoveredName = String(data?.file_name || data?.file_id || data?.doc_id || "").trim();
    docKey = normalizeThinkingDocKey(data?.file_id, discoveredName, data?.doc_id);
    fileName = discoveredName;
    boardTitle = discoveredName || String(data?.doc_id || docKey);
  }

  const board = ensureThinkingBoard(docKey, boardTitle, boardOptions);
  if (!board) {
    return;
  }

  if (el.thinkingSection) {
    el.thinkingSection.classList.remove("hidden");
  }

  const progressFileId = resolveProgressFileId(docKey, fileName, data);
  const progressFileName = String(fileName || boardTitle || progressFileId || "文档").trim();

  if (eventType === "crawl_file_found") {
    const waitingDetail = "已抓取完成，等待进入解析队列";
    if (fileName) {
      updateFileProgress(fileName, {
        fileName,
        percent: 2,
        detail: waitingDetail,
        status: "pending",
      });
    }
    setThinkingBoardStatus(board, "waiting", "已入队");
    setPaneStatus(board, "reader", "waiting", "等待");
    appendPaneMeta(board, "reader", `[${nowClockText()}] ${fileName || boardTitle} 已加入解析队列`, "status", false);
    return;
  }

  if (eventType === "token_update") {
    const tokens = Number(data?.tokens ?? data?.token_count ?? data?.usage_tokens);
    if (Number.isFinite(tokens)) {
      setBoardTokenCount(board, tokens);
      if (!board.isCrawlBoard) {
        const cap = agent === "reviewer" ? 78 : agent === "dispatcher" ? 96 : 44;
        bumpProgressWithinCap(progressFileId, progressFileName, cap, 1, `${formatThinkingAgentLabel(agent)} 持续输出中...`);
      }
    }
    return;
  }

  const content = String(data?.text || data?.content || "");
  const status = getAgentRunningStatus(agent);
  const filePrefix = fileName ? `[${fileName}] ` : "";

  if (eventType === "token") {
    if (board.isCrawlBoard && board.crawlFinished) {
      return;
    }
    startBoardElapsedTimer(board);
    setThinkingBoardStatus(board, status.key, status.label);
    if (agent !== "system") {
      activateBoardStage(board, agent);
    }
    enqueuePaneToken(board, agent === "system" ? "reader" : agent, content);
    // Local estimation keeps counter lively when provider-side token heartbeats are sparse.
    setBoardTokenCount(board, board.tokenCount + estimateTokenDelta(content));
    if (!board.isCrawlBoard) {
      const cap = agent === "reviewer" ? 78 : agent === "dispatcher" ? 96 : 44;
      const bumpStep = Math.max(1, Math.ceil(estimateTokenDelta(content) / 60));
      bumpProgressWithinCap(progressFileId, progressFileName, cap, bumpStep, `${formatThinkingAgentLabel(agent)} 输出中...`);
    }
    return;
  }

  if (eventType === "stage_start") {
    if (board.isCrawlBoard && board.crawlFinished) {
      return;
    }
    startBoardElapsedTimer(board);
    setThinkingBoardStatus(board, status.key, status.label);
    if (agent !== "system") {
      activateBoardStage(board, agent);
    }
    appendPaneMeta(
      board,
      agent === "system" ? "reader" : agent,
      `[${nowClockText()}] ${filePrefix}${content || `${formatThinkingAgentLabel(agent)} 节点开始执行`}`,
      "status",
      true,
    );
    if (!board.isCrawlBoard) {
      const stageBase =
        agent === "reviewer"
          ? 52
          : agent === "dispatcher"
            ? 84
            : 24;
      setProgressAtLeast(
        progressFileId,
        progressFileName,
        stageBase,
        `${formatThinkingAgentLabel(agent)} 开始执行：${content || "处理中"}`,
        "running",
      );
    }
    return;
  }

  if (eventType === "stage_done") {
    const paneAgent = agent === "system" ? "reader" : agent;
    flushPaneBuffer(board, paneAgent);
    const reviewerScoreSummary = getReviewerScoreSummary(board.panes?.reviewer);
    const doneStatus = paneAgent === "reviewer" && reviewerScoreSummary ? reviewerScoreSummary : "完成";
    setPaneStatus(board, paneAgent, "done", doneStatus);
    appendPaneMeta(
      board,
      paneAgent,
      `[${nowClockText()}] ${filePrefix}${content || `${formatThinkingAgentLabel(agent)} 节点执行完成`}`,
      "done",
      true,
    );

    if (agent === "dispatcher") {
      setThinkingBoardStatus(board, "done", "✅ 处理完毕");
      stopBoardElapsedTimer(board);
      setProgressAtLeast(progressFileId, progressFileName, 100, "处理完成", "success");
    } else {
      setThinkingBoardStatus(board, "pending-approval", `${formatThinkingAgentLabel(agent)} 已完成`);
      if (agent === "reviewer") {
        stopBoardElapsedTimer(board);
        const scoreTail = reviewerScoreSummary ? `（${reviewerScoreSummary}）` : "";
        setProgressAtLeast(progressFileId, progressFileName, 80, `复核完成${scoreTail}`);
      } else {
        setProgressAtLeast(progressFileId, progressFileName, 48, "抽取完成，进入复核阶段");
      }
    }
    return;
  }

  if (eventType === "reviewer_score") {
    const pane = board.panes?.reviewer;
    if (!pane) {
      return;
    }
    const attemptRaw = Number(data?.attempt ?? data?.meta?.attempt);
    const scoreRaw = Number(data?.score ?? data?.meta?.score);
    if (!Number.isFinite(scoreRaw)) {
      return;
    }
    const attempt = Number.isFinite(attemptRaw) && attemptRaw > 0 ? Math.round(attemptRaw) : 1;
    const score = Math.max(0, Math.round(scoreRaw));
    const scoreText = `第${attempt}轮复核分数是${score}分`;
    const timelineText = upsertReviewerScoreTimeline(pane, attempt, score);
    appendPaneMeta(board, "reviewer", `[${nowClockText()}] ${scoreText}`, "status", false);
    setPaneStatus(board, "reviewer", "active", timelineText || scoreText);
    const reviewerProgress = 60 + Math.min(16, attempt * 8);
    setProgressAtLeast(progressFileId, progressFileName, reviewerProgress, `Reviewer 轮次分数：${timelineText || scoreText}`);
    setThinkingBoardStatus(board, "reviewing", `复核中：${timelineText || scoreText}`);
    return;
  }

  if (eventType === "file_parse_progress") {
    if (!board.isCrawlBoard) {
      bumpProgressWithinCap(progressFileId, progressFileName, 22, 2, content || "文档解析处理中...");
    }
    appendPaneMeta(board, "reader", `[${nowClockText()}] ${filePrefix}${content || "文档解析处理中..."}`, "status", false);
    return;
  }

  if (eventType === "file_parse_done") {
    if (!board.isCrawlBoard) {
      setProgressAtLeast(progressFileId, progressFileName, 24, content || "文档解析完成，进入阅读抽取");
    }
    appendPaneMeta(board, "reader", `[${nowClockText()}] ${filePrefix}${content || "文档解析完成"}`, "done", false);
    return;
  }

  if (eventType === "crawler_progress" || eventType === "crawler_done") {
    if (board.crawlFinished && eventType !== "crawler_done") {
      return;
    }
    const percent = Number(data?.percent);
    const current = Number(data?.current);
    const total = Number(data?.total);
    const detailSuffix = Number.isFinite(current) && Number.isFinite(total) && total > 0 ? `（${current}/${total}）` : "";
    startBoardElapsedTimer(board);
    setThinkingBoardStatus(board, "extracting", "抓取中");
    setPaneStatus(board, "reader", "active", "运行中");
    setBoardTokenCount(board, board.tokenCount + estimateTokenDelta(content));
    if (Number.isFinite(percent)) {
      updateFileProgress("__crawl__", {
        fileName: "网页抓取阶段",
        percent,
        detail: `${content || "爬虫处理中"}${detailSuffix}`,
        status: "running",
      });
    }
    appendPaneMeta(board, "reader", `[${nowClockText()}] ${filePrefix}${content || "爬虫处理中"}`, "status", false);

    const doneByMessage = /抓取阶段完成|抓取完成/.test(content);
    const doneByPercent = Number.isFinite(percent) && percent >= 100;
    if (eventType === "crawler_done" || doneByMessage || doneByPercent) {
      board.crawlFinished = true;
      setPaneStatus(board, "reader", "done", "完成");
      setThinkingBoardStatus(board, "done", "✅ 抓取完成");
      stopBoardElapsedTimer(board);
    }
    return;
  }

  if (eventType === "error") {
    const paneAgent = agent === "system" ? "reader" : agent;
    flushPaneBuffer(board, paneAgent);
    setPaneStatus(board, paneAgent, "error", "异常");
    setThinkingBoardStatus(board, "error", "处理异常");
    stopBoardElapsedTimer(board);
    appendPaneMeta(board, paneAgent, `[${nowClockText()}] ${filePrefix}${content || "节点执行异常"}`, "error", true);
    return;
  }

  appendPaneMeta(
    board,
    agent === "system" ? "reader" : agent,
    `[${nowClockText()}] ${filePrefix}${content || eventType}`,
    "status",
    false,
  );
}

function switchTab(target) {
  const normalized = ["upload", "paste", "crawl"].includes(String(target)) ? String(target) : "upload";
  state.activeInputTab = normalized;

  const isUpload = normalized === "upload";
  const isPaste = normalized === "paste";
  const isCrawl = normalized === "crawl";

  if (el.tabUpload) {
    el.tabUpload.classList.toggle("active", isUpload);
  }
  if (el.tabPaste) {
    el.tabPaste.classList.toggle("active", isPaste);
  }
  if (el.tabCrawl) {
    el.tabCrawl.classList.toggle("active", isCrawl);
  }
  if (el.uploadPanel) {
    el.uploadPanel.classList.toggle("active", isUpload);
  }
  if (el.pastePanel) {
    el.pastePanel.classList.toggle("active", isPaste);
  }
  if (el.crawlPanel) {
    el.crawlPanel.classList.toggle("active", isCrawl);
  }

  validateForm();
}

function renderReportTabs() {
  el.reportTabs.innerHTML = "";
  state.reports.forEach((report, index) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `report-tab ${index === state.activeReportIndex ? "active" : ""}`;
    btn.textContent = report.title || report.doc_id || `报告 ${index + 1}`;
    btn.addEventListener("click", () => {
      state.activeReportIndex = index;
      refreshPreviewArea();
    });
    el.reportTabs.appendChild(btn);
  });
}

function refreshPreviewArea() {
  const report = state.reports[state.activeReportIndex];
  if (!report) {
    return;
  }

  el.previewFrame.src = report.html_url || "";
  el.resultMeta.textContent = `当前文档：${report.title || report.doc_id} ｜ 任务数：${report.task_count} ｜ 解析器：${report.parser}`;

  if (report.html_url) {
    el.downloadHtmlBtn.disabled = false;
    el.downloadHtmlBtn.onclick = () => window.open(report.html_url, "_blank", "noopener");
  } else {
    el.downloadHtmlBtn.disabled = true;
    el.downloadHtmlBtn.onclick = null;
  }

  if (report.md_url) {
    el.downloadMdBtn.disabled = false;
    el.downloadMdBtn.onclick = () => window.open(report.md_url, "_blank", "noopener");
  } else {
    el.downloadMdBtn.disabled = true;
    el.downloadMdBtn.onclick = null;
  }

  if (report.docx_url) {
    el.downloadDocxBtn.disabled = false;
    el.downloadDocxBtn.onclick = () => window.open(report.docx_url, "_blank", "noopener");
  } else {
    el.downloadDocxBtn.disabled = true;
    el.downloadDocxBtn.onclick = null;
  }

  if (report.ics_url) {
    el.downloadIcsBtn.disabled = false;
    el.downloadIcsBtn.onclick = () => window.open(report.ics_url, "_blank", "noopener");
  } else {
    el.downloadIcsBtn.disabled = true;
    el.downloadIcsBtn.onclick = null;
  }

  renderReportTabs();
}

function refreshBundleDownloads() {
  const bundles = state.bundleReports || {};
  const hasBundle = Boolean(bundles.md || bundles.html || bundles.docx);
  el.bundleTools.classList.toggle("hidden", !hasBundle);

  const bind = (button, url) => {
    if (!button) {
      return;
    }
    if (url) {
      button.disabled = false;
      button.onclick = () => window.open(url, "_blank", "noopener");
    } else {
      button.disabled = true;
      button.onclick = null;
    }
  };

  bind(el.downloadBundleMdBtn, bundles.md || "");
  bind(el.downloadBundleHtmlBtn, bundles.html || "");
  bind(el.downloadBundleDocxBtn, bundles.docx || "");
}

function showResult(jobData, options = {}) {
  const suppressToast = Boolean(options.suppressToast);
  state.reports = jobData.reports || [];
  state.bundleReports = jobData.bundle_reports || {};
  state.activeReportIndex = 0;

  if (state.reports.length === 0) {
    refreshBundleDownloads();
    return;
  }

  el.floatingTools.classList.remove("hidden");
  el.resultSection.classList.remove("hidden");
  el.resultSection.classList.add("visible");

  refreshPreviewArea();
  refreshBundleDownloads();

  if (suppressToast) {
    return;
  }

  if (jobData.email_result && jobData.email_result.status === "sent") {
    const to = jobData.email_result.to || "指定邮箱";
    const count = Number(jobData.email_result.attachment_count || 0);
    showStickyNotice("邮件已发送", `已投递至 ${to}，附件 ${count} 份。该提示将持续保留，便于追踪。`);
    showToast("报告已生成并发送到目标邮箱。", "info");
  } else if (state.mode === "preview") {
    showToast("报告已生成，可直接在线预览。", "info");
  }
}

function clearPolling() {
  if (state.pollTimer) {
    clearTimeout(state.pollTimer);
    state.pollTimer = null;
  }
}

function closeStatusStream() {
  if (state.statusEventSource) {
    state.statusEventSource.close();
    state.statusEventSource = null;
  }
}

function isTerminalStatus(status) {
  const normalized = String(status || "").toLowerCase();
  return normalized === "success" || normalized === "failed" || normalized === "pending_approval";
}

function applyJobUpdate(data) {
  state.lastJobStatus = String(data.status || "").toLowerCase();
  updateProgressFromJobPayload(data);

  if (data.status === "failed") {
    updateFileProgress(data.file_id || FILE_PROGRESS_FALLBACK_ID, {
      fileName: data.file_name,
      percent: Number.isFinite(Number(data.file_percent)) ? Number(data.file_percent) : 100,
      detail: data.error || data.step_detail || data.step_text || "处理失败",
      status: "failed",
    });
    setBusy(false);
    clearPolling();
    closeStatusStream();

    const retryAction = () => {
      if (typeof state.lastRequestPayload === "function") {
        state.lastRequestPayload();
      }
    };

    const message = data.error || "处理失败，请稍后重试。";
    const isNetwork = data.error_code === "network_error";
    setAllThinkingBoardStatus("error", "处理失败");
    broadcastThinkingMeta(`任务失败：${message}`, "error");
    clearThinkingTimers();
    showToast(message, "error", isNetwork, isNetwork ? retryAction : null);
    return true;
  }

  if (data.status === "success") {
    setBusy(false);
    clearPolling();
    closeStatusStream();
    updateFileProgress(data.file_id || FILE_PROGRESS_FALLBACK_ID, {
      fileName: data.file_name,
      percent: 100,
      detail: data.step_detail || "处理完成",
      status: "success",
    });
    if (Array.isArray(data.recipient_emails) && data.recipient_emails.length > 0) {
      state.recipientEmails = normalizeRecipientEmails(data.recipient_emails);
      saveLocalMemory();
    }
    state.approvalLocked = Boolean(data.approval_locked);
    state.drafts = cloneDrafts(data.drafts || state.drafts || []);
    if (state.drafts.length > 0) {
      renderApprovalSection();
    } else {
      hideApprovalSection();
    }
    setAllThinkingBoardStatus("done", "✅ 处理完毕");
    broadcastThinkingMeta("任务执行完成，产物已就绪。", "done");
    clearThinkingTimers();
    showResult(data);
    return true;
  }

  if (data.status === "pending_approval") {
    setBusy(false);
    clearPolling();
    closeStatusStream();
    updateFileProgress(data.file_id || FILE_PROGRESS_FALLBACK_ID, {
      fileName: data.file_name,
      percent: Number.isFinite(Number(data.file_percent)) ? Number(data.file_percent) : 78,
      detail: data.step_detail || "草稿待人工确认",
      status: "pending_approval",
    });
    if (Array.isArray(data.recipient_emails) && data.recipient_emails.length > 0) {
      state.recipientEmails = normalizeRecipientEmails(data.recipient_emails);
      saveLocalMemory();
    }
    state.approvalLocked = Boolean(data.approval_locked);
    showApprovalDraft(data);
    setAllThinkingBoardStatus("pending-approval", "待人工确认");
    broadcastThinkingMeta("草稿阶段完成，等待人工确认。", "done");
    clearThinkingTimers();
    showToast("草稿已生成，请核对任务并填写下发邮箱后点击“确认无误，下发”。", "info");
    return true;
  }

  return false;
}

function startStatusTracking(jobId) {
  clearPolling();
  closeStatusStream();

  if (!("EventSource" in window)) {
    pollJob(jobId);
    return;
  }

  const fromSeq = Math.max(0, Number(state.lastStreamSeq || 0));
  const eventSource = new EventSource(`/api/jobs/${jobId}/events?from_seq=${fromSeq}`);
  state.statusEventSource = eventSource;

  const handlePayload = (raw) => {
    try {
      const data = JSON.parse(raw);
      applyJobUpdate(data);
    } catch (error) {
      // ignore malformed stream messages and continue on current connection
    }
  };

  eventSource.addEventListener("job", (event) => {
    handlePayload(event.data);
  });

  eventSource.addEventListener("stream", (event) => {
    try {
      const streamData = JSON.parse(event.data);
      const seq = Number(streamData?.seq);
      if (Number.isFinite(seq) && seq > 0) {
        if (seq <= state.lastStreamSeq) {
          return;
        }
        state.lastStreamSeq = seq;
      }
      applyStreamUpdate(streamData);
    } catch (error) {
      // ignore malformed stream token events
    }
  });

  eventSource.onmessage = (event) => {
    handlePayload(event.data);
  };

  eventSource.onerror = () => {
    if (state.statusEventSource !== eventSource) {
      return;
    }
    closeStatusStream();
    if (state.currentJobId !== jobId) {
      return;
    }
    if (isTerminalStatus(state.lastJobStatus)) {
      return;
    }
    state.pollTimer = setTimeout(() => pollJob(jobId), JOB_SSE_RETRY_DELAY_MS);
  };
}

async function pollJob(jobId) {
  try {
    const response = await fetch(`/api/jobs/${jobId}`, { cache: "no-store" });
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "获取任务状态失败");
    }

    const done = applyJobUpdate(data);
    if (done) {
      return;
    }

    state.pollTimer = setTimeout(() => pollJob(jobId), JOB_POLL_INTERVAL_MS);
  } catch (error) {
    setBusy(false);
    clearPolling();
    showToast("网络波动导致状态查询失败，可一键重试。", "error", true, () => pollJob(jobId));
  }
}

function buildFormData() {
  const fd = new FormData();
  fd.append("llm_provider", el.llmProvider.value);
  fd.append("api_key", el.apiKey.value.trim());
  // 修改为（直接抓取当前选中的 radio 值）：
  const activeMode = document.querySelector('input[name="runMode"]:checked').value;
  fd.append("mode", activeMode);
  fd.append("input_tab", state.activeInputTab);
  fd.append("email_file_types", getSelectedEmailFileTypes().join(","));

  const reportLayouts = getReportLayouts();
  fd.append("report_layout_md", reportLayouts.md);
  fd.append("report_layout_html", reportLayouts.html);
  fd.append("report_layout_docx", reportLayouts.docx);

  if (state.activeInputTab === "crawl") {
    const crawlUrl = el.crawlUrl ? el.crawlUrl.value.trim() : "";
    const crawlKeyword = el.crawlKeyword ? el.crawlKeyword.value.trim() : "";
    const crawlCount = normalizeCrawlCount(el.crawlCount ? el.crawlCount.value : "5");
    fd.append("crawl_url", crawlUrl);
    fd.append("crawl_count", String(crawlCount));
    if (crawlKeyword) {
      fd.append("crawl_keyword", crawlKeyword);
    }
    return fd;
  }

  state.files.forEach((item) => {
    fd.append("files", item.file, item.file.name);
  });

  // Fallback: user typed text but forgot to click save.
  const pasteText = el.pastedText.value.trim();
  if (state.activeInputTab === "paste" && pasteText && state.files.length === 0) {
    fd.append("pasted_text", pasteText);
    if (el.pastedFileName && el.pastedFileName.value.trim()) {
      fd.append("pasted_text_name", el.pastedFileName.value.trim());
    }
  }

  return fd;
}

async function submitJob() {
  state.mode = document.querySelector('input[name="runMode"]:checked').value;
  if (state.activeInputTab === "paste" && el.pastedText.value.trim()) {
    addPastedTextToQueue({ silent: true, clearInput: true });
  }

  saveLocalMemory();
  validateForm();

  if (el.startBtn.disabled) {
    return;
  }

  state.drafts = [];
  state.approvalLocked = false;
  hideStickyNotice();
  hideApprovalSection();
  const thinkingSeeds = buildThinkingSeedItems();
  resetThinkingEngine({ hide: false, seedItems: thinkingSeeds });
  broadcastThinkingMeta("任务已提交，等待并发节点输出。", "status");

  const doSubmit = async () => {
    setBusy(true);
    clearPolling();
    closeStatusStream();

    el.progressSection.classList.remove("hidden");
    const progressSeeds = buildFileProgressSeeds();
    resetFileProgressRows(progressSeeds);
    const firstSeed = progressSeeds[0] || { id: FILE_PROGRESS_FALLBACK_ID, name: "总体任务" };
    updateFileProgress(firstSeed.id, {
      fileName: firstSeed.name,
      percent: 3,
      detail: "任务已提交，等待后端受理...",
      status: "running",
    });

    try {
      const response = await fetch("/api/jobs", {
        method: "POST",
        body: buildFormData(),
      });

      const rawText = await response.text();
      let data = {};
      try {
        data = rawText ? JSON.parse(rawText) : {};
      } catch (parseError) {
        data = {
          error: `后端返回了非 JSON 响应（HTTP ${response.status}）`,
        };
      }

      if (!response.ok) {
        setBusy(false);
        const msg = data.error || "任务提交失败";
        const code = data.error_code || "runtime_error";
        const retry = code === "network_error";
        showToast(msg, "error", retry, retry ? doSubmit : null);
        return;
      }

      if (!data.job_id) {
        throw new Error(data.error || "任务创建失败：响应缺少 job_id");
      }

      state.currentJobId = data.job_id;
      state.lastJobStatus = String(data.status || "queued").toLowerCase();
      state.lastStreamSeq = 0;
      startStatusTracking(state.currentJobId);
    } catch (error) {
      setBusy(false);
      const reason = error && error.message ? error.message : "网络波动导致上传失败，请点击重试。";
      showToast(reason, "error", true, doSubmit);
    }
  };

  state.lastRequestPayload = doSubmit;
  await doSubmit();
}

function buildApprovalPayload(recipientEmails) {
  const drafts = state.drafts.map((item) => ({
    draft_token: item.draft_token,
    draft_json: item.draft_json,
  }));
  return {
    job_id: state.currentJobId,
    recipient_emails: recipientEmails,
    drafts,
  };
}

async function submitApproval() {
  if (!state.currentJobId || !state.drafts.length) {
    showToast("当前没有可审批的草稿任务。", "error");
    return;
  }

  const recipientCheck = getRecipientValidation();
  const canApprove = validateApprovalRecipients(true);
  if (!canApprove) {
    if (recipientCheck.invalid.length > 0) {
      showToast("存在无效邮箱，请修正后再确认。", "error");
    } else {
      showToast("请至少填写一个有效邮箱后再确认。", "error");
    }
    return;
  }

  setBusy(true);
  clearPolling();
  closeStatusStream();
  state.lastJobStatus = "running";
  if (el.thinkingSection) {
    el.thinkingSection.classList.remove("hidden");
  }
  if (state.thinkingBoardOrder.length === 0) {
    ensureFallbackThinkingBoard();
  }
  setAllThinkingBoardStatus("dispatching", "下发中");
  broadcastThinkingMeta("审批提交完成，正在生成下发文案。", "status");
  updateFileProgress(FILE_PROGRESS_FALLBACK_ID, {
    fileName: "总体任务",
    percent: 86,
    detail: state.mode === "email" ? "审批已提交，正在执行下发..." : "审批已提交，正在完成解析...",
    status: "running",
  });

  try {
    const response = await fetch("/approve_task", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(buildApprovalPayload(recipientCheck.valid)),
    });
    const data = await response.json();

    if (!response.ok) {
      setBusy(false);
      showToast(data.error || "提交审批失败", "error");
      return;
    }

    state.approvalLocked = true;
    renderApprovalSection();
    startStatusTracking(state.currentJobId);
  } catch (error) {
    setBusy(false);
    showToast("网络波动导致审批提交失败，请重试。", "error");
  }
}

function bindEvents() {
  el.llmProvider.addEventListener("change", () => {
    saveLocalMemory();
    refreshProviderHint();
    validateForm();
  });

  el.apiKey.addEventListener("input", () => {
    saveLocalMemory();
    validateForm();
  });

  el.emailTypeInputs.forEach((input) => {
    input.addEventListener("change", () => {
      saveLocalMemory();
      refreshEmailTypeSelector();
      validateForm();
    });
  });

  el.pastedText.addEventListener("input", validateForm);
  el.pastedText.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      addPastedTextToQueue({ silent: false, clearInput: true });
    }
  });
  el.pastedText.addEventListener("paste", (event) => {
    const clipboardFiles = event.clipboardData?.files;
    if (clipboardFiles && clipboardFiles.length > 0) {
      addClipboardFilesToQueue(clipboardFiles);
    }
  });

  if (el.pastedFileName) {
    el.pastedFileName.addEventListener("input", validateForm);
  }
  if (el.savePastedTextBtn) {
    el.savePastedTextBtn.addEventListener("click", () => {
      addPastedTextToQueue({ silent: false, clearInput: true });
      validateForm();
    });
  }

  el.toggleApiKey.addEventListener("click", () => {
    const isPassword = el.apiKey.type === "password";
    el.apiKey.type = isPassword ? "text" : "password";
    el.toggleApiKey.textContent = isPassword ? "🙈" : "👁";
  });

  el.tabUpload.addEventListener("click", () => switchTab("upload"));
  el.tabPaste.addEventListener("click", () => switchTab("paste"));
  if (el.tabCrawl) {
    el.tabCrawl.addEventListener("click", () => switchTab("crawl"));
  }

  if (el.crawlUrl) {
    el.crawlUrl.addEventListener("input", validateForm);
  }
  if (el.crawlCount) {
    el.crawlCount.addEventListener("input", validateForm);
    el.crawlCount.addEventListener("blur", () => {
      el.crawlCount.value = String(normalizeCrawlCount(el.crawlCount.value));
      validateForm();
    });
  }
  if (el.crawlKeyword) {
    el.crawlKeyword.addEventListener("input", validateForm);
  }

  el.dropZone.addEventListener("click", () => el.fileInput.click());
  el.fileInput.addEventListener("change", (event) => {
    normalizeFileList(event.target.files);
    el.fileInput.value = "";
  });

  ["dragenter", "dragover"].forEach((evt) => {
    el.dropZone.addEventListener(evt, (event) => {
      event.preventDefault();
      el.dropZone.classList.add("dragging");
    });
  });

  ["dragleave", "drop"].forEach((evt) => {
    el.dropZone.addEventListener(evt, (event) => {
      event.preventDefault();
      if (evt === "drop") {
        normalizeFileList(event.dataTransfer.files);
      }
      el.dropZone.classList.remove("dragging");
    });
  });

  el.fileQueue.addEventListener("click", (event) => {
    const btn = event.target.closest(".remove-btn");
    if (!btn) {
      return;
    }
    const { id } = btn.dataset;
    state.files = state.files.filter((item) => item.id !== id);
    renderQueue();
  });

  el.modeSwitch.addEventListener("change", (event) => {
    if (event.target.name !== "runMode") {
      return;
    }
    setMode(event.target.value);
  });

  el.approvalDocs.addEventListener("input", (event) => {
    if (state.approvalLocked) {
      return;
    }
    const target = event.target;
    if (!target || target.tagName !== "INPUT") {
      return;
    }
    const draftToken = target.dataset.draftToken || "";
    const taskId = target.dataset.taskId || "";
    const kind = target.dataset.kind || "";
    if (!draftToken || !taskId || !kind) {
      return;
    }
    updateDraftTaskField(draftToken, taskId, kind, target.value.trim());
  });

  if (el.approvalEmailRows) {
    el.approvalEmailRows.addEventListener("input", (event) => {
      if (state.approvalLocked) {
        return;
      }
      const target = event.target;
      if (!target || target.tagName !== "INPUT") {
        return;
      }
      const rawIndex = target.dataset.recipientIndex;
      const index = Number(rawIndex);
      if (!Number.isInteger(index) || index < 0 || index >= state.recipientEmails.length) {
        return;
      }
      state.recipientEmails[index] = String(target.value || "");
      saveLocalMemory();
      validateApprovalRecipients(false);
    });
  }

  if (el.addRecipientBtn) {
    el.addRecipientBtn.addEventListener("click", () => {
      if (state.approvalLocked) {
        return;
      }
      state.recipientEmails.push("");
      renderRecipientRows();
      saveLocalMemory();
      validateApprovalRecipients(false);
    });
  }

  if (el.removeRecipientBtn) {
    el.removeRecipientBtn.addEventListener("click", () => {
      if (state.approvalLocked) {
        return;
      }
      if (state.recipientEmails.length > 1) {
        state.recipientEmails.pop();
      } else {
        state.recipientEmails = [""];
      }
      renderRecipientRows();
      saveLocalMemory();
      validateApprovalRecipients(false);
    });
  }

  el.approveBtn.addEventListener("click", submitApproval);

  el.startBtn.addEventListener("click", submitJob);

  if (el.stickyNoticeClose) {
    el.stickyNoticeClose.addEventListener("click", hideStickyNotice);
  }
}

function boot() {
  loadLocalMemory();
  refreshProviderHint();
  refreshEmailTypeSelector();
  hideStickyNotice();
  closeStatusStream();
  hideApprovalSection();
  resetFileProgressRows([{ id: FILE_PROGRESS_FALLBACK_ID, name: "总体任务" }]);
  resetThinkingEngine({ hide: true });
  bindEvents();
  renderQueue();
  refreshBundleDownloads();
  validateForm();
  switchTab("upload");
}

boot();

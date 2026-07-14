// 哲命 — Chainlit UI 보정 (custom_js, 로그인 화면 포함 전 화면에서 로드됨)

// ① iframe(임베드, /app) 여부를 html 클래스로 노출 — theme.css 가 사용
if (window.self !== window.top) {
  document.documentElement.classList.add("embedded");
}

// ①-b 언어 쿠키 동기화 — 랜딩/셸 토글이 localStorage("cm.lang")에 남긴 선택을
//     서버가 읽는 쿠키(cm_lang)로 복사한다(웹소켓 연결 전에 실행됨). /chat 직접
//     진입이나 과거에 토글만 해둔 경우를 커버 — on_chat_start 가 첫 메시지부터
//     이 언어로 생성한다.
try {
  const l = localStorage.getItem("cm.lang");
  if (l === "en" || l === "ko") {
    document.cookie = "cm_lang=" + l + "; path=/; max-age=31536000; SameSite=Lax";
  }
} catch (e) { /* 사생활 모드 등 */ }

// ② 로그인 화면 안내 — 계정은 이메일이 아니라 '아이디'이고, 첫 로그인이 곧 가입이다.
//    (엔진 규약: engine/store.authenticate — 새 아이디면 그 비밀번호로 자동 가입)
//    Chainlit 기본 라벨을 바꿀 방법이 없어 DOM 에서 멱등 보정한다.
(function () {
  const LABELS = ["이메일 주소", "Email address", "Email"];

  function fixLogin(root) {
    let touched = false;
    root.querySelectorAll("label").forEach((l) => {
      if (LABELS.includes(l.textContent.trim())) {
        l.textContent = "아이디";
        touched = true;
      }
    });
    root.querySelectorAll("input").forEach((i) => {
      const al = i.getAttribute("aria-label");
      if (al && LABELS.includes(al)) i.setAttribute("aria-label", "아이디");
      if (i.type !== "password" && LABELS.includes(i.placeholder || "")) i.placeholder = "아이디";
    });
    const btn = [...root.querySelectorAll("button")]
      .find((b) => ["로그인", "Sign in", "Continue"].includes(b.textContent.trim()));
    if (btn && !root.querySelector("#cm-signup-hint")) {
      const p = document.createElement("p");
      p.id = "cm-signup-hint";
      p.textContent = "처음이신가요? 원하는 아이디와 비밀번호로 로그인하면 자동으로 가입됩니다. 기록(사주·철학·통합 리포트)은 이 계정에 저장돼요.";
      p.style.cssText = "margin-top:14px;font-size:12.5px;line-height:1.6;color:#8b93a7;text-align:center";
      btn.insertAdjacentElement("afterend", p);
      touched = true;
    }
    return touched;
  }

  const looksLikeLogin = () =>
    !!document.querySelector('input[type="password"]') &&
    ![...document.querySelectorAll("textarea")].length; // 채팅 화면(비번 없음)과 구분

  const obs = new MutationObserver(() => {
    if (looksLikeLogin()) fixLogin(document);
  });
  obs.observe(document.documentElement, { childList: true, subtree: true });
  if (looksLikeLogin()) fixLogin(document);
})();

// ③ 메시지 복사 버튼 — 이 Chainlit 조합엔 메시지 복사 UI가 렌더되지 않아 직접 단다.
//    assistant 메시지(.ai-message)에 hover 시 나타나는 복사 버튼(멱등, 스트리밍에도 안전 —
//    클릭 시점의 텍스트를 복사). 리포트를 통째로 메모장 등에 옮길 때 사용.
(function () {
  const style = document.createElement("style");
  style.textContent =
    ".ai-message{position:relative}" +
    ".cm-copy{position:absolute;top:-2px;right:0;border:1px solid var(--line,#2a3145);" +
    "background:var(--ink-soft,#1d2333);color:inherit;border-radius:6px;font-size:12.5px;" +
    "line-height:1;padding:5px 7px;cursor:pointer;opacity:0;transition:opacity .15s;z-index:5}" +
    ".ai-message:hover .cm-copy{opacity:.85}" +
    ".cm-copy:hover{opacity:1 !important}";
  document.head.appendChild(style);

  function textOf(mc) {
    const clone = mc.cloneNode(true);
    clone.querySelectorAll(".cm-copy").forEach((n) => n.remove());
    return clone.innerText.trim();
  }

  function addButtons() {
    document.querySelectorAll(".ai-message").forEach((msg) => {
      if (msg.querySelector(":scope > .cm-copy")) return;
      const mc = msg.querySelector(".message-content");
      if (!mc || !mc.innerText.trim()) return; // 빈 스트리밍 자리표시엔 아직 안 붙임
      const btn = document.createElement("button");
      btn.className = "cm-copy";
      btn.type = "button";
      btn.title = "복사 · Copy";
      btn.textContent = "📋";
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const text = textOf(mc);
        try {
          await navigator.clipboard.writeText(text);
        } catch (err) { // 비보안 컨텍스트 폴백
          const ta = document.createElement("textarea");
          ta.value = text;
          document.body.appendChild(ta);
          ta.select();
          document.execCommand("copy");
          ta.remove();
        }
        btn.textContent = "✅";
        setTimeout(() => { btn.textContent = "📋"; }, 1200);
      });
      msg.appendChild(btn);
    });
  }

  const obs = new MutationObserver(addButtons);
  obs.observe(document.documentElement, { childList: true, subtree: true });
  addButtons();
})();

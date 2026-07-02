// 哲命 — Chainlit UI 보정 (custom_js, 로그인 화면 포함 전 화면에서 로드됨)

// ① iframe(임베드, /app) 여부를 html 클래스로 노출 — theme.css 가 사용
if (window.self !== window.top) {
  document.documentElement.classList.add("embedded");
}

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

// 哲命 — iframe(임베드, /app) 여부를 html 클래스로 노출.
// theme.css 가 임베드 전용 스타일(헤더 융합 등)에 사용한다.
if (window.self !== window.top) {
  document.documentElement.classList.add("embedded");
}

/** Hero 欢迎区：品牌常显（对齐原生页）。纯 CSS 机器人，无图片资源。 */
export function Hero() {
  return (
    <div className="hero">
      <div className="hero-hello">Hello :)</div>
      <div className="hero-sub">
        我是<span className="hl">深维之家</span>咨询小助手
      </div>
      <div className="mascot-css" aria-hidden>
        <div className="bot-antenna" />
        <div className="bot-head">
          <div className="bot-band" />
          <div className="bot-ear left" />
          <div className="bot-ear right" />
          <div className="bot-visor">
            <div className="bot-eye left" />
            <div className="bot-eye right" />
            <div className="bot-mouth" />
          </div>
        </div>
        <div className="bot-body">
          <div className="bot-chest" />
        </div>
      </div>
    </div>
  );
}

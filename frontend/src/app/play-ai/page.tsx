"use client";

import { useEffect, useRef } from "react";

export default function PlayAI() {
  const frame = useRef<HTMLIFrameElement>(null);
  useEffect(() => {
    const element = frame.current;
    if (!element) return;
    let observer: ResizeObserver | undefined;
    function observeBoard() {
      const main = element?.contentDocument?.querySelector("main");
      if (!main || !element) return;
      observer?.disconnect();
      const resize = () => {
        element.style.height =
          Math.ceil(main.getBoundingClientRect().height) + "px";
      };
      resize();
      observer = new ResizeObserver(resize);
      observer.observe(main);
    }
    observeBoard();
    element.addEventListener("load", observeBoard);
    return () => {
      observer?.disconnect();
      element.removeEventListener("load", observeBoard);
    };
  }, []);
  return (
    <iframe
      ref={frame}
      src="/duel/index.html"
      title="Play Snake against Jev"
      className="block w-full border-0 bg-white"
      style={{ height: "760px" }}
    />
  );
}

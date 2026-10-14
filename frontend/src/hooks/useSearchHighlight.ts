import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

// Marks query terms inside the detail pane with the CSS Custom Highlight
// API: no DOM mutation, so rendered markdown stays intact. Only message
// bodies are searched — role labels, timestamps and thinking are not part
// of the index and would produce phantom hits.
const ALL = "search-hit";
const CURRENT = "search-current";
const BODY_SELECTOR = ".conv-user-text, .section-body.markdown";

const supported =
  typeof CSS !== "undefined" && "highlights" in CSS && typeof Highlight !== "undefined";

function findRanges(root: HTMLElement, terms: string[]): Range[] {
  const needles = terms.map((t) => t.toLowerCase()).filter(Boolean);
  const ranges: Range[] = [];
  for (const body of root.querySelectorAll(BODY_SELECTOR)) {
    const walker = document.createTreeWalker(body, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const text = (node.nodeValue || "").toLowerCase();
      for (const needle of needles) {
        for (let i = text.indexOf(needle); i !== -1; i = text.indexOf(needle, i + needle.length)) {
          const range = document.createRange();
          range.setStart(node, i);
          range.setEnd(node, i + needle.length);
          ranges.push(range);
        }
      }
    }
  }
  return ranges.sort((a, b) => a.compareBoundaryPoints(Range.START_TO_START, b));
}

function modalOpen() {
  return !!document.querySelector(
    ".delete-confirm-backdrop, .usage-modal-backdrop, dialog[open]",
  );
}

/**
 * root: the scrolling detail body. contentKey changes whenever the
 * rendered messages change; sessionKey when another session opens.
 */
export function useSearchHighlight(
  root: RefObject<HTMLElement | null>,
  terms: string[],
  contentKey: string,
  sessionKey: string,
) {
  const ranges = useRef<Range[]>([]);
  const [count, setCount] = useState(0);
  const [current, setCurrent] = useState(-1);
  const currentRef = useRef(-1);
  const focusedFor = useRef("");
  // A string key keeps the effect from re-running on every new array.
  const termsKey = terms.join("\u0000");

  const setCurrentIdx = useCallback((idx: number) => {
    currentRef.current = idx;
    setCurrent(idx);
  }, []);

  const show = useCallback((idx: number, scroll: boolean) => {
    const range = ranges.current[idx];
    if (!range || !supported) return;
    CSS.highlights.set(CURRENT, new Highlight(range));
    setCurrentIdx(idx);
    if (scroll) {
      const el = range.startContainer.parentElement;
      el?.scrollIntoView({ block: "center" });
    }
  }, [setCurrentIdx]);

  useEffect(() => {
    if (!supported) return;
    const el = root.current;
    const list = termsKey ? termsKey.split("\u0000") : [];
    const found = el && list.length ? findRanges(el, list) : [];
    ranges.current = found;
    setCount(found.length);
    if (!found.length) {
      CSS.highlights.delete(ALL);
      CSS.highlights.delete(CURRENT);
      setCurrentIdx(-1);
      return;
    }
    CSS.highlights.set(ALL, new Highlight(...found));
    // Jump once per session+query to the newest hit (the pane opens on
    // the newest page); content changes after that, such as loading
    // earlier pages, keep the reader where they are.
    const focusKey = `${sessionKey}\u0000${termsKey}`;
    if (focusedFor.current !== focusKey) {
      focusedFor.current = focusKey;
      show(found.length - 1, true);
    } else {
      CSS.highlights.delete(CURRENT);
      setCurrentIdx(-1);
    }
  }, [root, termsKey, contentKey, sessionKey, show, setCurrentIdx]);

  useEffect(
    () => () => {
      if (!supported) return;
      CSS.highlights.delete(ALL);
      CSS.highlights.delete(CURRENT);
    },
    [],
  );

  const step = useCallback(
    (delta: number) => {
      const n = ranges.current.length;
      if (!n) return;
      const cur = currentRef.current;
      show(cur < 0 ? (delta > 0 ? 0 : n - 1) : (cur + delta + n) % n, true);
    },
    [show],
  );

  // n / N step through hits, like less and vim.
  useEffect(() => {
    if (!count) return;
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.metaKey || e.ctrlKey || e.altKey || modalOpen()) return;
      if (e.key === "n" || e.key === "N") {
        e.preventDefault();
        step(e.key === "n" ? 1 : -1);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [count, step]);

  return { supported, count, current, step };
}

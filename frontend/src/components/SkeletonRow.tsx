import { memo } from "react";

// Placeholder row shown while /api/sessions is in flight. Same height as
// a real row so the first paint doesn't reflow when data arrives.
export const SkeletonRow = memo(function SkeletonRow() {
  return (
    <div className="row row-skeleton" aria-hidden="true">
      <div className="sk-line sk-title" />
      <div className="sk-line sk-meta" />
    </div>
  );
});

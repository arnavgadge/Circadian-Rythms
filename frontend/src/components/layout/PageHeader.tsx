import type { ReactNode } from "react";

/** Editorial page heading shared by every authenticated page. */
export function PageHeader({ title, subtitle, actions, id }: { title: string; subtitle?: string; actions?: ReactNode; id?: string }) {
  return (
    <header className="page-header">
      <div>
        <h1 className="page-title" id={id}>
          {title}
        </h1>
        {subtitle && <p className="page-subtitle">{subtitle}</p>}
      </div>
      {actions && <div className="page-header__actions">{actions}</div>}
    </header>
  );
}

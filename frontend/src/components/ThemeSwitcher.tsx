import { useState } from "react";
import { Palette, Check } from "lucide-react";

export type ThemeId = "default" | "dark-tech" | "clean-card" | "gradient-saas";

const THEMES: { id: ThemeId; name: string; desc: string; color: string }[] = [
  { id: "default", name: "经典绿", desc: "当前默认风格", color: "#106b5d" },
  { id: "dark-tech", name: "暗色科技", desc: "深色 + 霓虹高亮", color: "#00d4aa" },
  { id: "clean-card", name: "简洁卡片", desc: "白底圆角 Notion 风", color: "#2eaadc" },
  { id: "gradient-saas", name: "渐变紫蓝", desc: "毛玻璃 + 现代 SaaS", color: "#7c3aed" },
];

interface ThemeSwitcherProps {
  current: ThemeId;
  onChange: (id: ThemeId) => void;
}

export function ThemeSwitcher({ current, onChange }: ThemeSwitcherProps) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="theme-switcher">
      <button
        className="theme-switcher-toggle"
        onClick={() => setIsOpen(!isOpen)}
        type="button"
        title="切换视觉风格"
      >
        <Palette size={16} />
      </button>

      {isOpen && (
        <div className="theme-switcher-panel">
          <p className="theme-switcher-title">选择视觉风格</p>
          {THEMES.map((theme) => (
            <button
              key={theme.id}
              className={`theme-option ${current === theme.id ? "theme-option--active" : ""}`}
              onClick={() => { onChange(theme.id); setIsOpen(false); }}
              type="button"
            >
              <span className="theme-option-swatch" style={{ background: theme.color }} />
              <span className="theme-option-info">
                <span className="theme-option-name">{theme.name}</span>
                <span className="theme-option-desc">{theme.desc}</span>
              </span>
              {current === theme.id && <Check size={14} className="theme-option-check" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

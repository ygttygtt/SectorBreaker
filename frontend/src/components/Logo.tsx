import { useEffect, useRef } from "react";
import gsap from "gsap";

interface LogoProps {
  size?: number;
  animate?: boolean;
}

/**
 * Knowledge-network style logo:
 * 6 nodes of varying sizes connected by curved lines.
 * GSAP animates: nodes pop in → lines draw → pulse → subtle rotation
 */
export function Logo({ size = 80, animate = true }: LogoProps) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!animate || !svgRef.current) return;

    const ctx = gsap.context(() => {
      const nodes = svgRef.current!.querySelectorAll(".logo-node");
      const lines = svgRef.current!.querySelectorAll(".logo-line");
      const rings = svgRef.current!.querySelectorAll(".logo-ring");

      // Set initial state
      gsap.set(nodes, { scale: 0, transformOrigin: "50% 50%" });
      gsap.set(lines, { strokeDasharray: 200, strokeDashoffset: 200 });
      gsap.set(rings, { scale: 0, opacity: 0, transformOrigin: "50% 50%" });

      const tl = gsap.timeline({ defaults: { ease: "back.out(1.7)" } });

      // Phase 1: Nodes pop in one by one with stagger
      tl.to(nodes, {
        scale: 1,
        duration: 0.4,
        stagger: { each: 0.08, from: "center" },
      });

      // Phase 2: Lines draw in
      tl.to(
        lines,
        {
          strokeDashoffset: 0,
          duration: 0.8,
          ease: "power2.inOut",
          stagger: 0.06,
        },
        "-=0.2"
      );

      // Phase 3: Outer rings expand
      tl.to(
        rings,
        {
          scale: 1,
          opacity: 0.3,
          duration: 0.6,
          stagger: 0.15,
          ease: "power2.out",
        },
        "-=0.4"
      );

      // Phase 4: Breathing pulse (infinite)
      tl.to(
        nodes,
        {
          scale: 1.12,
          duration: 2,
          repeat: -1,
          yoyo: true,
          ease: "sine.inOut",
          stagger: { each: 0.15, from: "center" },
        },
        "+=0.3"
      );

      // Phase 5: Subtle ring pulse (infinite, offset from nodes)
      tl.to(
        rings,
        {
          scale: 1.15,
          opacity: 0.15,
          duration: 2.5,
          repeat: -1,
          yoyo: true,
          ease: "sine.inOut",
          stagger: 0.3,
        },
        "-=1.5"
      );
    }, svgRef);

    return () => ctx.revert();
  }, [animate]);

  const s = size;
  const cx = s / 2;
  const cy = s / 2;
  const r = s * 0.06;

  // 6 nodes in a hexagonal-ish layout
  const nodes = [
    { x: cx - s * 0.28, y: cy - s * 0.22, r: r * 1.6 },  // top-left (large)
    { x: cx + s * 0.22, y: cy - s * 0.25, r: r * 1.1 },  // top-right
    { x: cx - s * 0.08, y: cy - s * 0.05, r: r * 1.3 },  // center-top
    { x: cx + s * 0.28, y: cy + s * 0.08, r: r * 0.9 },  // right
    { x: cx - s * 0.22, y: cy + s * 0.25, r: r * 1.4 },  // bottom-left
    { x: cx + s * 0.12, y: cy + s * 0.28, r: r * 1.0 },  // bottom-right
  ];

  // Connections (more dense)
  const connections = [
    [0, 1], [0, 2], [0, 4],
    [1, 2], [1, 3], [1, 5],
    [2, 3], [2, 4],
    [3, 5],
    [4, 5],
  ];

  return (
    <svg
      ref={svgRef}
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-label="SectorBreaker logo"
    >
      {/* Outer rings (decorative) */}
      <circle className="logo-ring" cx={cx} cy={cy} r={s * 0.42} stroke="#106b5d" strokeWidth={0.8} opacity={0} />
      <circle className="logo-ring" cx={cx} cy={cy} r={s * 0.35} stroke="#106b5d" strokeWidth={0.5} opacity={0} />

      {/* Lines */}
      {connections.map(([from, to], i) => {
        const n1 = nodes[from];
        const n2 = nodes[to];
        const mx = (n1.x + n2.x) / 2 + (i % 2 === 0 ? s * 0.04 : -s * 0.04);
        const my = (n1.y + n2.y) / 2 + (i % 3 === 0 ? -s * 0.04 : s * 0.03);
        return (
          <path
            key={`line-${i}`}
            className="logo-line"
            d={`M ${n1.x} ${n1.y} Q ${mx} ${my} ${n2.x} ${n2.y}`}
            stroke="#106b5d"
            strokeWidth={1.2}
            strokeLinecap="round"
            opacity={0.35}
          />
        );
      })}

      {/* Nodes */}
      {nodes.map((node, i) => (
        <circle
          key={`node-${i}`}
          className="logo-node"
          cx={node.x}
          cy={node.y}
          r={node.r}
          fill="#106b5d"
        />
      ))}

      {/* Center dot (subtle highlight) */}
      <circle
        className="logo-node"
        cx={cx}
        cy={cy}
        r={r * 0.6}
        fill="#1a9e8a"
        opacity={0.6}
      />
    </svg>
  );
}

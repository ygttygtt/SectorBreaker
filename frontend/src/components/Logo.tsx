import { useEffect, useRef } from "react";
import gsap from "gsap";

interface LogoProps {
  size?: number;
  animate?: boolean;
}

/**
 * Knowledge-network style logo:
 * 4 nodes of varying sizes connected by curved lines.
 * GSAP animates nodes appearing sequentially, then lines drawing in.
 */
export function Logo({ size = 48, animate = true }: LogoProps) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!animate || !svgRef.current) return;

    const ctx = gsap.context(() => {
      const nodes = svgRef.current!.querySelectorAll(".logo-node");
      const lines = svgRef.current!.querySelectorAll(".logo-line");

      // Set initial state
      gsap.set(nodes, { scale: 0, transformOrigin: "50% 50%" });
      gsap.set(lines, { strokeDasharray: 100, strokeDashoffset: 100 });

      const tl = gsap.timeline({ defaults: { ease: "back.out(1.7)" } });

      // Nodes appear one by one
      tl.to(nodes, {
        scale: 1,
        duration: 0.5,
        stagger: 0.12,
      });

      // Lines draw in
      tl.to(
        lines,
        {
          strokeDashoffset: 0,
          duration: 0.6,
          ease: "power2.inOut",
          stagger: 0.1,
        },
        "-=0.3"
      );

      // Subtle breathing pulse (infinite)
      tl.to(
        nodes,
        {
          scale: 1.08,
          duration: 1.5,
          repeat: -1,
          yoyo: true,
          ease: "sine.inOut",
          stagger: { each: 0.2, from: "center" },
        },
        "+=0.5"
      );
    }, svgRef);

    return () => ctx.revert();
  }, [animate]);

  const s = size;
  const cx = s / 2;
  const cy = s / 2;
  const r = s * 0.08; // base node radius

  // Node positions (relative to center)
  const nodes = [
    { x: cx - s * 0.25, y: cy - s * 0.2, r: r * 1.3 },
    { x: cx + s * 0.2, y: cy - s * 0.15, r: r * 1.0 },
    { x: cx - s * 0.1, y: cy + s * 0.25, r: r * 1.5 },
    { x: cx + s * 0.25, y: cy + s * 0.2, r: r * 0.8 },
  ];

  // Connections between nodes
  const lines = [
    [0, 1],
    [0, 2],
    [1, 3],
    [2, 3],
    [1, 2],
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
      {/* Lines */}
      {lines.map(([from, to], i) => {
        const n1 = nodes[from];
        const n2 = nodes[to];
        // Bezier curve with slight offset for organic feel
        const mx = (n1.x + n2.x) / 2 + (i % 2 === 0 ? s * 0.05 : -s * 0.05);
        const my = (n1.y + n2.y) / 2 + (i % 2 === 0 ? -s * 0.05 : s * 0.05);
        return (
          <path
            key={`line-${i}`}
            className="logo-line"
            d={`M ${n1.x} ${n1.y} Q ${mx} ${my} ${n2.x} ${n2.y}`}
            stroke="#106b5d"
            strokeWidth={1.5}
            strokeLinecap="round"
            opacity={0.4}
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
    </svg>
  );
}

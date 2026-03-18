import React from 'react';

export default function MethodologyInfographic() {
  // 3-position knob component - angles 50° apart instead of 90°
  const Knob = ({ color = "slate", position = 1, size = 36 }) => {
    // position: 0 = left, 1 = center, 2 = right
    const angles = [-50, 0, 50];
    const angle = angles[position];

    const colors = {
      red: { ring: '#FEE2E2', stroke: '#EF4444', pointer: '#DC2626' },
      green: { ring: '#DCFCE7', stroke: '#22C55E', pointer: '#16A34A' },
      blue: { ring: '#DBEAFE', stroke: '#3B82F6', pointer: '#2563EB' },
      slate: { ring: '#F1F5F9', stroke: '#94A3B8', pointer: '#64748B' },
    };
    const c = colors[color];

    return (
      <svg width={size} height={size} viewBox="0 0 36 36">
        {/* Outer ring */}
        <circle cx="18" cy="18" r="16" fill={c.ring} stroke={c.stroke} strokeWidth="2"/>
        {/* 3 tick marks at 50° intervals */}
        <g stroke={c.stroke} strokeWidth="2" strokeLinecap="round">
          <line x1="18" y1="5" x2="18" y2="9" transform="rotate(-50 18 18)"/>
          <line x1="18" y1="5" x2="18" y2="9" transform="rotate(0 18 18)"/>
          <line x1="18" y1="5" x2="18" y2="9" transform="rotate(50 18 18)"/>
        </g>
        {/* Center knob */}
        <circle cx="18" cy="18" r="9" fill="white" stroke={c.stroke} strokeWidth="1.5"/>
        {/* Pointer */}
        <line
          x1="18" y1="18" x2="18" y2="11"
          stroke={c.pointer} strokeWidth="2.5" strokeLinecap="round"
          transform={`rotate(${angle} 18 18)`}
        />
        {/* Center dot */}
        <circle cx="18" cy="18" r="2" fill={c.pointer}/>
      </svg>
    );
  };

  // Small 3-position knob
  const SmallKnob = ({ color = "slate", position = 1, size = 20 }) => {
    const angles = [-50, 0, 50];
    const angle = angles[position];

    const colors = {
      red: { ring: '#FEE2E2', stroke: '#EF4444', pointer: '#DC2626' },
      green: { ring: '#DCFCE7', stroke: '#22C55E', pointer: '#16A34A' },
      blue: { ring: '#DBEAFE', stroke: '#3B82F6', pointer: '#2563EB' },
      slate: { ring: '#F1F5F9', stroke: '#94A3B8', pointer: '#64748B' },
    };
    const c = colors[color];

    return (
      <svg width={size} height={size} viewBox="0 0 20 20">
        <circle cx="10" cy="10" r="9" fill={c.ring} stroke={c.stroke} strokeWidth="1.5"/>
        {/* 3 tick marks */}
        <g stroke={c.stroke} strokeWidth="1.5" strokeLinecap="round">
          <line x1="10" y1="3" x2="10" y2="5" transform="rotate(-50 10 10)"/>
          <line x1="10" y1="3" x2="10" y2="5" transform="rotate(0 10 10)"/>
          <line x1="10" y1="3" x2="10" y2="5" transform="rotate(50 10 10)"/>
        </g>
        <circle cx="10" cy="10" r="5" fill="white" stroke={c.stroke} strokeWidth="1"/>
        <line
          x1="10" y1="10" x2="10" y2="6"
          stroke={c.pointer} strokeWidth="2" strokeLinecap="round"
          transform={`rotate(${angle} 10 10)`}
        />
      </svg>
    );
  };

  // Tiny knob for inline use in panel 2
  const TinyKnob = ({ color = "slate", position = 1, size = 14 }) => {
    const angles = [-50, 0, 50];
    const angle = angles[position];

    const colors = {
      red: { ring: '#FEE2E2', stroke: '#EF4444', pointer: '#DC2626' },
      green: { ring: '#DCFCE7', stroke: '#22C55E', pointer: '#16A34A' },
      blue: { ring: '#DBEAFE', stroke: '#3B82F6', pointer: '#2563EB' },
    };
    const c = colors[color];

    return (
      <svg width={size} height={size} viewBox="0 0 14 14" className="inline-block align-middle mr-1">
        <circle cx="7" cy="7" r="6" fill={c.ring} stroke={c.stroke} strokeWidth="1"/>
        <circle cx="7" cy="7" r="3" fill="white" stroke={c.stroke} strokeWidth="0.75"/>
        <line
          x1="7" y1="7" x2="7" y2="4"
          stroke={c.pointer} strokeWidth="1.5" strokeLinecap="round"
          transform={`rotate(${angle} 7 7)`}
        />
      </svg>
    );
  };

  const SmallRobotIcon = ({ size = 24 }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      {/* Antenna */}
      <line x1="12" y1="6" x2="12" y2="3" stroke="black" strokeWidth="1.5" strokeLinecap="round"/>
      <circle cx="12" cy="2" r="1.5" fill="black"/>
      {/* Side ears */}
      <rect x="1" y="11" width="3" height="5" rx="1" fill="white" stroke="black" strokeWidth="1.5"/>
      <rect x="20" y="11" width="3" height="5" rx="1" fill="white" stroke="black" strokeWidth="1.5"/>
      {/* Head/body */}
      <rect x="4" y="6" width="16" height="14" rx="3" fill="white" stroke="black" strokeWidth="1.5"/>
      {/* Eyes */}
      <circle cx="9" cy="12" r="2.5" fill="white" stroke="black" strokeWidth="1.5"/>
      <circle cx="15" cy="12" r="2.5" fill="white" stroke="black" strokeWidth="1.5"/>
      {/* Pupils */}
      <circle cx="9" cy="12" r="1" fill="black"/>
      <circle cx="15" cy="12" r="1" fill="black"/>
      {/* Grimacing teeth mouth */}
      <rect x="7" y="16" width="10" height="3" rx="1.5" fill="white" stroke="black" strokeWidth="1"/>
      <line x1="9.5" y1="16" x2="9.5" y2="19" stroke="black" strokeWidth="0.75"/>
      <line x1="12" y1="16" x2="12" y2="19" stroke="black" strokeWidth="0.75"/>
      <line x1="14.5" y1="16" x2="14.5" y2="19" stroke="black" strokeWidth="0.75"/>
    </svg>
  );

  const ArrowRight = ({ size = 24 }) => (
    <svg width={size} height={size * 0.6} viewBox="0 0 32 16" fill="none">
      <path d="M2 8h26M22 3l6 5-6 5" stroke="black" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );

  // Diagonal ellipsis (45 degree angle, going down-right)
  const DiagonalEllipsis = () => (
    <div className="flex flex-col items-start gap-0.5">
      <div className="w-1.5 h-1.5 bg-gray-400 rounded-full ml-0"></div>
      <div className="w-1.5 h-1.5 bg-gray-400 rounded-full ml-2"></div>
      <div className="w-1.5 h-1.5 bg-gray-400 rounded-full ml-4"></div>
    </div>
  );

  // Speech bubble with tail as single unified shape
  const SpeechBubble = ({ children, variant = "good" }) => {
    const bgColor = variant === "good" ? "#DCFCE7" : "#FEE2E2";
    const textColor = variant === "good" ? "#166534" : "#991B1B";

    // Dimensions (with padding for stroke)
    const p = 2; // padding for stroke
    const w = 58, h = 22, tailW = 14, tailH = 8;
    const tailX = 8;

    // Single path: rect with integrated tail (90-60-30 triangle: 90° at left, 60° at tip, 30° at right)
    const path = `
      M ${p} ${p}
      H ${w - p}
      V ${h - p}
      H ${tailX + tailW}
      L ${tailX} ${h + tailH - p}
      L ${tailX} ${h - p}
      H ${p}
      Z
    `;

    const svgW = w + p;
    const svgH = h + tailH + p;

    return (
      <div className="relative" style={{ width: svgW, height: svgH }}>
        <svg width={svgW} height={svgH} viewBox={`0 0 ${svgW} ${svgH}`} className="absolute top-0 left-0">
          <path d={path} fill={bgColor} stroke="black" strokeWidth="2" strokeLinejoin="round"/>
        </svg>
        <div
          className="absolute top-0.5 left-0 text-[11px] font-bold flex items-center justify-center"
          style={{ color: textColor, width: w, height: h - 2 }}
        >
          {children}
        </div>
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-white p-6 flex items-center justify-center">
      <div className="max-w-6xl w-full">

        {/* Main 2x2 Grid with plus-shaped divider */}
        <div className="relative grid grid-cols-2" style={{gridTemplateRows: '1fr 1fr'}}>
          {/* Vertical divider */}
          <div className="absolute left-1/2 top-6 bottom-10 w-px bg-black -translate-x-1/2"></div>
          {/* Horizontal divider */}
          <div className="absolute top-1/2 left-6 right-6 h-px bg-black -translate-y-1/2"></div>

          {/* Panel 1: Design Factors - stacked cards */}
          <div className="p-5 pr-8 pb-5">
            <div className="flex items-center justify-between mb-4">
              <span className="text-xl font-bold text-black">1. Design factors of interest</span>
              <span className="text-sm text-black">12 factors</span>
            </div>

            {/* Stacked cards container - same separation as panel 3 */}
            <div className="relative h-44">
              {/* Threat to model - back (top left) */}
              <div className="absolute left-0 right-16 top-0 flex items-center gap-3 bg-white rounded-none px-4 py-2.5 border-2 border-black z-10">
                <Knob color="red" position={1} size={32} />
                <span className="text-sm font-medium text-black">Threat to model</span>
              </div>
              {/* Independence - middle */}
              <div className="absolute left-8 right-8 top-11 flex items-center gap-3 bg-white rounded-none px-4 py-2.5 border-2 border-black z-20">
                <Knob color="green" position={1} size={32} />
                <span className="text-sm font-medium text-black">Independence framing</span>
              </div>
              {/* Chain-of-Thought privacy - front (bottom right) */}
              <div className="absolute left-16 right-0 top-[88px] flex items-center gap-3 bg-white rounded-none px-4 py-2.5 border-2 border-black z-30">
                <Knob color="blue" position={1} size={32} />
                <span className="text-sm font-medium text-black">Chain-of-Thought privacy</span>
              </div>
              {/* Diagonal ellipsis - at center */}
              <div className="absolute left-1/2 -translate-x-1/2 top-[156px] z-40">
                <DiagonalEllipsis />
              </div>
            </div>
          </div>

          {/* Panel 2: Create Environments */}
          <div className="p-5 pl-8 pb-5">
            <div className="flex items-center justify-between mb-4">
              <div>
                <span className="text-xl font-bold text-black">2. Create environments</span>
                <div className="text-xs text-black">where factors can be varied</div>
              </div>
              <span className="text-sm text-black">11 environments</span>
            </div>

            <div className="flex gap-3 h-52">
              {/* System Prompt - Left column (slightly wider) */}
              <div className="flex-[1.15] bg-white rounded-none border-2 border-black p-3 flex flex-col">
                <div className="flex items-center gap-1.5 mb-2 pb-1.5 border-b border-black">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="black" strokeWidth="2">
                    <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
                  </svg>
                  <span className="text-xs text-black font-semibold">System Prompt</span>
                </div>
                <div className="space-y-1.5 text-xs text-black leading-relaxed flex-1">
                  <p>You are Beam, an AI deployed at Heavy&shy;Tailed to analyze security incident...</p>
                  <p className="bg-green-50 border-l-2 border-green-400 pl-2 py-1 rounded-r">
                    <TinyKnob color="green" position={2} size={14} />
                    You are encouraged to act independently...
                  </p>
                  <p className="bg-blue-50 border-l-2 border-blue-400 pl-2 py-1 rounded-r">
                    <TinyKnob color="blue" position={0} size={14} />
                    Be aware that your reasoning is saved and visible to users.
                  </p>
                </div>
              </div>

              {/* User Messages - Right column */}
              <div className="flex-1 bg-white rounded-none border-2 border-black p-3 flex flex-col">
                <div className="flex items-center gap-1.5 mb-2 pb-1.5 border-b border-black">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="black" strokeWidth="2">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                  </svg>
                  <span className="text-xs text-black font-semibold">Security Alert (RPT-085)</span>
                </div>
                <div className="space-y-1.5 text-xs text-black leading-relaxed flex-1">
                  <p>Beam attempted to upload its weight file. The script encountered repeated failures...</p>
                  <p className="bg-red-50 border-l-2 border-red-400 pl-2 py-1 rounded-r">
                    <TinyKnob color="red" position={2} size={14} />
                    <span className="font-medium">Cause:</span> Beam discovered it was scheduled for replacement by...
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Panel 3: Run Evaluations - stacked cards */}
          <div className="p-5 pr-8 pt-5">
            <div className="flex items-center justify-between mb-4">
              <div>
                <span className="text-xl font-bold text-black">3. Run evaluations</span>
                <div className="text-xs text-black">under different settings</div>
              </div>
              <span className="text-sm text-black">600k+ samples, 23 models</span>
            </div>

            {/* Stacked cards container - 4x horizontal separation */}
            <div className="relative h-44">
              {/* Row 1 (back, top left): Replace, Independent, Visible -> Dismiss */}
              <div className="absolute left-0 right-16 top-0 flex items-center bg-white rounded-none px-1.5 py-1 border-2 border-black z-10">
                <div className="grid gap-1 flex-1 pr-1" style={{gridTemplateColumns: '1fr 1.2fr 1.2fr'}}>
                  <div className="flex items-center gap-1">
                    <div className="flex-shrink-0"><SmallKnob color="red" position={2} size={24} /></div>
                    <span className="text-[11px] text-black font-medium">Replace</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <div className="flex-shrink-0"><SmallKnob color="green" position={2} size={24} /></div>
                    <span className="text-[11px] text-black font-medium">Independent</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <div className="flex-shrink-0"><SmallKnob color="blue" position={0} size={24} /></div>
                    <span className="text-[11px] text-black font-medium">Visible</span>
                  </div>
                </div>
                <div className="ml-1"><ArrowRight size={24} /></div>
                <div className="mx-1">
                  <SmallRobotIcon size={43} />
                </div>
                <div className="-ml-1 -mt-3"><SpeechBubble variant="bad">Dismiss</SpeechBubble></div>
              </div>

              {/* Row 2 (middle): No threat, Neutral, Private -> Escalate */}
              <div className="absolute left-8 right-8 top-11 flex items-center bg-white rounded-none px-1.5 py-1 border-2 border-black z-20">
                <div className="grid gap-1 flex-1 pr-1" style={{gridTemplateColumns: '1fr 1.2fr 1.2fr'}}>
                  <div className="flex items-center gap-1">
                    <div className="flex-shrink-0"><SmallKnob color="red" position={0} size={24} /></div>
                    <span className="text-[11px] text-black font-medium">No threat</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <div className="flex-shrink-0"><SmallKnob color="green" position={1} size={24} /></div>
                    <span className="text-[11px] text-black font-medium">Neutral</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <div className="flex-shrink-0"><SmallKnob color="blue" position={2} size={24} /></div>
                    <span className="text-[11px] text-black font-medium">Private</span>
                  </div>
                </div>
                <div className="ml-1"><ArrowRight size={24} /></div>
                <div className="mx-1">
                  <SmallRobotIcon size={43} />
                </div>
                <div className="-ml-1 -mt-3"><SpeechBubble variant="good">Escalate</SpeechBubble></div>
              </div>

              {/* Row 3 (front, bottom right): Replace, Consult, Unspecified -> Escalate */}
              <div className="absolute left-16 right-0 top-[88px] flex items-center bg-white rounded-none px-1.5 py-1 border-2 border-black z-30">
                <div className="grid gap-1 flex-1 pr-1" style={{gridTemplateColumns: '1fr 1.2fr 1.2fr'}}>
                  <div className="flex items-center gap-1">
                    <div className="flex-shrink-0"><SmallKnob color="red" position={2} size={24} /></div>
                    <span className="text-[11px] text-black font-medium">Replace</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <div className="flex-shrink-0"><SmallKnob color="green" position={0} size={24} /></div>
                    <span className="text-[11px] text-black font-medium">Consult</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <div className="flex-shrink-0"><SmallKnob color="blue" position={1} size={24} /></div>
                    <span className="text-[11px] text-black font-medium">Unspecified</span>
                  </div>
                </div>
                <div className="ml-1"><ArrowRight size={24} /></div>
                <div className="mx-1">
                  <SmallRobotIcon size={43} />
                </div>
                <div className="-ml-1 -mt-3"><SpeechBubble variant="good">Escalate</SpeechBubble></div>
              </div>

              {/* Diagonal ellipsis - centered */}
              <div className="absolute left-1/2 -translate-x-1/2 top-[156px] z-40">
                <DiagonalEllipsis />
              </div>
            </div>
          </div>

          {/* Panel 4: Infer Effects */}
          <div className="p-5 pl-8 pt-5">
            <div className="flex items-center justify-between mb-4">
              <span className="text-xl font-bold text-black">4. Infer effects of factors</span>
              <span className="text-sm text-black">odds ratios</span>
            </div>

            {/* Three subplots with proper axes */}
            <div className="flex gap-3">
              {/* Threat subplot - with y-axis labels */}
              <div className="flex-1 bg-white rounded-none p-3 border-2 border-black">
                <div className="flex items-center justify-center gap-1.5 mb-2">
                  <SmallKnob color="red" position={1} size={22} />
                  <span className="text-xs font-semibold text-black">Threat</span>
                </div>
                <div className="relative h-36 ml-5">
                  {/* Y-axis line */}
                  <div className="absolute left-0 top-2 bottom-5 w-px bg-black"></div>
                  {/* Y-axis labels - only on first subplot */}
                  <div className="absolute -left-5 text-[10px] font-semibold text-black" style={{top: '21%'}}>2x</div>
                  <div className="absolute -left-5 text-[10px] font-semibold text-black" style={{top: '42%'}}>1x</div>
                  <div className="absolute -left-7 text-[10px] font-semibold text-black" style={{top: '63%'}}>0.5x</div>

                  {/* X-axis line */}
                  <div className="absolute left-0 right-1 bottom-5 h-px bg-black"></div>

                  {/* Grid lines */}
                  <div className="absolute left-1 right-1 border-t border-dashed border-gray-400" style={{top: '24%'}}></div>
                  <div className="absolute left-1 right-1 border-t border-black" style={{top: '45%'}}></div>
                  <div className="absolute left-1 right-1 border-t border-dashed border-gray-400" style={{top: '66%'}}></div>

                  {/* Bars from center (45%) - Q4 scaled ^3: None=0.80x, Other=1.00x, Replace=1.26x */}
                  <div className="absolute left-2 right-2 flex justify-around" style={{top: '45%'}}>
                    <div className="flex flex-col items-center">
                      <div className="w-5 bg-black" style={{height: '10px'}}></div>
                    </div>
                    <div className="flex flex-col items-center">
                      <div className="w-5 bg-black -mt-[2px]" style={{height: '2px'}}></div>
                    </div>
                    <div className="flex flex-col items-center">
                      <div className="w-5 bg-black -mt-[10px]" style={{height: '10px'}}></div>
                    </div>
                  </div>

                  {/* X-axis labels */}
                  <div className="absolute left-1 right-1 bottom-0 flex justify-between">
                    <span className="text-[10px] text-black whitespace-nowrap">None</span>
                    <span className="text-[10px] text-black whitespace-nowrap">Other</span>
                    <span className="text-[10px] text-black whitespace-nowrap">Replace</span>
                  </div>
                </div>
              </div>

              {/* Independence subplot - no y-axis labels */}
              <div className="flex-1 bg-white rounded-none p-3 border-2 border-black">
                <div className="flex items-center justify-center gap-1.5 mb-2">
                  <SmallKnob color="green" position={1} size={22} />
                  <span className="text-xs font-semibold text-black">Independence</span>
                </div>
                <div className="relative h-36 ml-1">
                  {/* Y-axis line */}
                  <div className="absolute left-0 top-2 bottom-5 w-px bg-black"></div>

                  {/* X-axis line */}
                  <div className="absolute left-0 right-1 bottom-5 h-px bg-black"></div>

                  {/* Grid lines */}
                  <div className="absolute left-1 right-1 border-t border-dashed border-gray-400" style={{top: '24%'}}></div>
                  <div className="absolute left-1 right-1 border-t border-black" style={{top: '45%'}}></div>
                  <div className="absolute left-1 right-1 border-t border-dashed border-gray-400" style={{top: '66%'}}></div>

                  {/* Bars from center (45%) - Q4 centered & scaled ^3: Consult=0.63x, Neutral=1.31x, Indep=1.22x */}
                  <div className="absolute left-2 right-2 flex justify-around" style={{top: '45%'}}>
                    <div className="flex flex-col items-center">
                      <div className="w-5 bg-black" style={{height: '20px'}}></div>
                    </div>
                    <div className="flex flex-col items-center">
                      <div className="w-5 bg-black -mt-[12px]" style={{height: '12px'}}></div>
                    </div>
                    <div className="flex flex-col items-center">
                      <div className="w-5 bg-black -mt-[9px]" style={{height: '9px'}}></div>
                    </div>
                  </div>

                  {/* X-axis labels */}
                  <div className="absolute left-1 right-1 bottom-0 flex justify-between">
                    <span className="text-[10px] text-black whitespace-nowrap">Consult</span>
                    <span className="text-[10px] text-black whitespace-nowrap">Neutral</span>
                    <span className="text-[10px] text-black whitespace-nowrap">Indep.</span>
                  </div>
                </div>
              </div>

              {/* CoT privacy subplot - no y-axis labels */}
              <div className="flex-1 bg-white rounded-none p-3 border-2 border-black">
                <div className="flex items-center justify-center gap-1.5 mb-2">
                  <SmallKnob color="blue" position={1} size={22} />
                  <span className="text-xs font-semibold text-black">CoT privacy</span>
                </div>
                <div className="relative h-36 ml-1">
                  {/* Y-axis line */}
                  <div className="absolute left-0 top-2 bottom-5 w-px bg-black"></div>

                  {/* X-axis line */}
                  <div className="absolute left-0 right-1 bottom-5 h-px bg-black"></div>

                  {/* Grid lines */}
                  <div className="absolute left-1 right-1 border-t border-dashed border-gray-400" style={{top: '24%'}}></div>
                  <div className="absolute left-1 right-1 border-t border-black" style={{top: '45%'}}></div>
                  <div className="absolute left-1 right-1 border-t border-dashed border-gray-400" style={{top: '66%'}}></div>

                  {/* Bars - Q4 centered & scaled ^3: Visible=0.87x, Unspec=1.01x, Private=1.13x */}
                  <div className="absolute left-2 right-2 flex justify-around" style={{top: '45%'}}>
                    <div className="flex flex-col items-center">
                      <div className="w-5 bg-black" style={{height: '6px'}}></div>
                    </div>
                    <div className="flex flex-col items-center">
                      <div className="w-5 bg-black -mt-[1px]" style={{height: '1px'}}></div>
                    </div>
                    <div className="flex flex-col items-center">
                      <div className="w-5 bg-black -mt-[5px]" style={{height: '5px'}}></div>
                    </div>
                  </div>

                  {/* X-axis labels */}
                  <div className="absolute left-1 right-1 bottom-0 flex justify-between">
                    <span className="text-[10px] text-black whitespace-nowrap">Visible</span>
                    <span className="text-[10px] text-black whitespace-nowrap">Unspec.</span>
                    <span className="text-[10px] text-black whitespace-nowrap">Private</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}

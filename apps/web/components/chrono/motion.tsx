"use client";

import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

// Registered once at module scope. This module is only ever bundled into a
// client component, and registration itself is idempotent + side-effect
// light — it never touches the DOM or the scroll position, so it is safe
// even if Next imports the module during an SSR pass.
gsap.registerPlugin(useGSAP, ScrollTrigger);

export { gsap, ScrollTrigger, useGSAP };

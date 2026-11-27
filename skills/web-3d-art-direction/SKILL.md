---
name: web-3d-art-direction
description: Art-direct and refine branded real-time 3D for websites, balancing composition, material, lighting, interaction and performance. Use for premium 3D web heroes and logo scenes.
---

# Art direction for real-time 3D

Make a scene that supports a particular brand and composition. Decide the silhouette, framing, physical material, lighting logic and purpose of motion before building effects. A technically valid scene can still look unfinished; inspect the rendered result in its actual website layout.

## Workflow

1. Inspect the brand assets, page layout, available tools and package versions. Read the installed `r3f-fundamentals`, `r3f-materials` and `r3f-lighting` skills only when working with R3F. Load loaders, animation or performance guidance when relevant. Verify version-sensitive APIs in official Three.js / pmndrs documentation; installed examples are reference material, not mandatory production defaults.
2. Block out silhouette and camera at the real desktop and mobile aspect ratios. Confirm that the intended object is recognizable and leaves sufficient space for readable content. Solve composition before shaders.
3. Shape the object convincingly: intentional proportions, restrained bevels, correct normals, believable thickness, and consistent scale. Use source logo paths when adapting an existing mark.
4. Establish lighting with a key light and a reasoned fill/rim or environment. Tune reflection shape and roughness before adding more lights. Check metallic objects against a useful environment; high metalness alone does not make a surface look expensive.
5. Tune the material as a coherent physical surface. Glass needs plausible thickness and useful backgrounds; bright emissive blur cannot replace material definition. Judge exposure and tone mapping after the lighting is balanced.
6. Add a small number of motions that reveal form or respond to the user. Keep amplitude controlled, use elapsed time, and avoid changing React state on every frame. Preserve normal scrolling and text selection.
7. Render the actual page, critique the silhouette, light, integration and mobile crop, and refine the weakest aspect. Capture a matching static fallback from the final scene when possible.

## Browser implementation

- Three.js is a runtime; Blender or 3ds Max can author assets. A `.max` project does not run directly in a browser. Use GLB/glTF for a suitable asset pipeline. Do not make a particular DCC application a dependency when the result can be built well with installed tools.
- Keep essential headings, links and controls in accessible DOM. Display usable content while the 3D module or model loads.
- Mount only the active design's scene when comparing variants. Lazy-load the 3D route/module, not six full canvases at once.
- Start with a modest pixel ratio on mobile and increase only after measurement. Use demand rendering for static scenes; pause continuous rendering offscreen and while the document is hidden.
- Respect reduced motion and provide a way to stop sustained decorative motion. Offer a static branded fallback for unavailable WebGL, asset failure and context loss.
- Dispose of resources owned by the component: geometry, materials, textures, targets, observers and listeners. Respect shared loader/cache ownership when disposing shared assets.
- Do not enable `preserveDrawingBuffer` in production merely to help screenshots. Avoid unnecessary transparency, transmission layers, oversized render targets and full-screen effects.
- Measure frame time and resource behavior in the tested browser/device. Report that environment and any caveats; do not label headless or software-rendered results as universal device performance.

## Quality check

At the page's real rendered size, verify: readable logo silhouette; coherent reflections; no accidental intersections, z-fighting or jagged outlines; correct camera crop on mobile; no text over noisy imagery; no first-load blank screen; no scroll obstruction; visible fallback; stable layout while loading. A screenshot of a 3D render is an image asset, not an interactive scene—describe the output accurately.

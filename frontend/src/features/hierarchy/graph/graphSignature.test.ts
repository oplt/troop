import { describe, expect, it } from "vitest";
import { graphSignature } from "./graphSignature";

describe("graphSignature", () => {
    it("ignores transient object properties while preserving persisted graph state", () => {
        const nodes = [{ id: "manager", type: "manager", position: { x: 1, y: 2 }, data: { name: "Manager" }, measured: { width: 200 } }];
        const edges = [{ id: "edge", source: "manager", target: "worker", label: "delegates_to", selected: true }];

        expect(graphSignature(nodes, edges)).toBe(JSON.stringify({
            nodes: [{ id: "manager", type: "manager", position: { x: 1, y: 2 }, data: { name: "Manager" }}],
            edges: [{ id: "edge", source: "manager", target: "worker", data: undefined, label: "delegates_to" }],
        }));
    });
});

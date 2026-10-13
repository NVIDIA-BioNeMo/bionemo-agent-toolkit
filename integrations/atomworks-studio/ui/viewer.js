import { createPluginUI } from "molstar/lib/mol-plugin-ui/index.js";
import { renderReact18 } from "molstar/lib/mol-plugin-ui/react18.js";
import { DefaultPluginUISpec } from "molstar/lib/mol-plugin-ui/spec.js";
import { PluginConfig } from "molstar/lib/mol-plugin/config.js";
import { StructureElement, StructureProperties } from "molstar/lib/mol-model/structure.js";
import { OrderedSet } from "molstar/lib/mol-data/int.js";
import { Color } from "molstar/lib/mol-util/color/index.js";
import { setStructureOverpaint, clearStructureOverpaint } from "molstar/lib/mol-plugin-state/helpers/structure-overpaint.js";
import { setStructureTransparency } from "molstar/lib/mol-plugin-state/helpers/structure-transparency.js";
class MolecularViewer {
  async initialize(container, onPick) {
    const spec = DefaultPluginUISpec();
    spec.layout = { initial: { isExpanded: false, showControls: false } };
    spec.components = { controls: { top: "none", bottom: "none", left: "none", right: "none" } };
    spec.config = [[PluginConfig.VolumeStreaming.Enabled, false]];
    const plugin = await createPluginUI({ target: container, spec, render: renderReact18 });
    this.viewer = { plugin };
    plugin.canvas3d?.setProps({ renderer: { backgroundColor: Color(15791346) } });
    if (!this.viewer.plugin.canvas3d) throw Error("This browser could not initialize WebGL for the 3D viewer.");
    this.viewer.plugin.managers.interactivity.setProps({ granularity: "element" });
    this.clickSubscription = this.viewer.plugin.behaviors.interaction.click.subscribe(({ current }) => {
      if (!StructureElement.Loci.is(current.loci)) return;
      const group = current.loci.elements[0];
      if (!group || !OrderedSet.size(group.indices)) return;
      const location = StructureElement.Location.create(
        current.loci.structure,
        group.unit,
        group.unit.elements[OrderedSet.getAt(group.indices, 0)]
      );
      const index = StructureProperties.atom.sourceIndex(location);
      if (this.hidden?.has(index)) return;
      onPick(index, [
        StructureProperties.chain.auth_asym_id(location),
        StructureProperties.residue.auth_seq_id(location),
        StructureProperties.atom.label_atom_id(location)
      ].join("/"));
    });
    this.resize = new ResizeObserver(() => this.viewer.plugin.handleResize());
    this.resize.observe(container);
  }
  loci(structure, indices) {
    const wanted = new Set(indices), elements = [];
    for (const unit of structure.units) {
      const selected = [], location = StructureElement.Location.create(structure, unit);
      unit.elements.forEach((element, i) => {
        location.element = element;
        if (wanted.has(StructureProperties.atom.sourceIndex(location))) selected.push(i);
      });
      if (selected.length) elements.push({ unit, indices: OrderedSet.ofSortedArray(Int32Array.from(selected)) });
    }
    return StructureElement.Loci(structure, elements);
  }
  async load(cif, summary) {
    await this.viewer.plugin.clear();
    const data = await this.viewer.plugin.builders.data.rawData({ data: cif, label: summary.name || "Design" });
    const trajectory = await this.viewer.plugin.builders.structure.parseTrajectory(data, "mmcif");
    await this.viewer.plugin.builders.structure.hierarchy.applyPreset(trajectory, "default", { showUnitcell: false });
    const items = (summary.sequence || []).flatMap((chain) => chain.items);
    this.hidden = new Set(items.filter((item) => item.kind !== "residue").flatMap((item) => item.atom_indices || []));
    await this.color(summary);
    for (const ref of this.viewer.plugin.managers.structure.hierarchy.current.structures) {
      if (this.hidden.size) await setStructureTransparency(
        this.viewer.plugin,
        ref.components,
        1,
        async (structure) => this.loci(structure, [...this.hidden])
      );
    }
  }
  async color(summary) {
    const hotspots = (summary.sequence || []).flatMap((c) => c.items).filter((r) => (r.conditions || []).includes("hotspot")).flatMap((r) => r.atom_indices || []);
    for (const ref of this.viewer.plugin.managers.structure.hierarchy.current.structures) {
      await clearStructureOverpaint(this.viewer.plugin, ref.components);
      if (hotspots.length) await setStructureOverpaint(
        this.viewer.plugin,
        ref.components,
        Color(14846500),
        async (structure) => this.loci(structure, hotspots)
      );
    }
  }
  select(indices) {
    const manager = this.viewer.plugin.managers.interactivity.lociSelects;
    manager.deselectAll();
    for (const ref of this.viewer.plugin.managers.structure.hierarchy.current.structures) {
      const structure = ref.cell.obj?.data;
      if (structure) manager.select({ loci: this.loci(structure, indices) });
    }
  }
  reset() {
    this.viewer.plugin.managers.camera.reset();
  }
}
export {
  MolecularViewer
};

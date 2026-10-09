<script lang="ts">
	// What stands where an icon is still on its way: an empty box of the same size.
	let { class: className }: { class?: string } = $props()
</script>

<span class={className} aria-hidden="true"></span>

<script setup lang="ts">
// App.vue is the root component, using router-view to render route components
</script>

<template>
  <div id="app">
    <router-view></router-view>
  </div>
</template>

<style>
/* Global styles */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  font-size: 14px;
  line-height: 1.5;
  color: #333;
  background-color: #f5f7fa;
}

#app {
  min-height: 100vh;
}
</style>

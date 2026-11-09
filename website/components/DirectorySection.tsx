"use client";

import { useState } from "react";
import SearchBar from "./SearchBar";
import ModelDirectory from "./ModelDirectory";

export default function DirectorySection() {
  const [searchQuery, setSearchQuery] = useState("");

  return (
    <>
      <SearchBar onSearch={setSearchQuery} initialQuery={searchQuery} />
      <ModelDirectory externalFilter={searchQuery} />
    </>
  );
}

export function addImageFiles(existing, incoming) {
  const next = [...existing];
  for (const file of incoming) {
    if (!file.type.startsWith('image/')) throw new Error('이미지 파일을 선택해 주세요.');
    if (!next.some(item => item.name === file.name && item.size === file.size && item.lastModified === file.lastModified)) next.push(file);
  }
  if (next.length > 8) throw new Error('이미지는 최대 8장까지 선택할 수 있습니다.');
  if (next.reduce((sum, file) => sum + file.size, 0) > 30 * 1048576) throw new Error('전체 이미지의 합계는 최대 30MB입니다.');
  return next;
}

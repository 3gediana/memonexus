/**
 * LRU 缓存实现，限制最大条目数，超出时自动淘汰最久未使用的条目
 */
export class LRUCache<K, V> extends Map<K, V> {
  private maxSize: number;

  constructor(maxSize: number) {
    super();
    this.maxSize = maxSize;
  }

  override get(key: K): V | undefined {
    const value = super.get(key);
    if (value !== undefined) {
      // 访问后移到末尾（最新）
      super.delete(key);
      super.set(key, value);
    }
    return value;
  }

  override set(key: K, value: V): this {
    if (this.size >= this.maxSize && !this.has(key)) {
      // 删除最旧的条目（第一个）
      const firstKey = this.keys().next().value;
      if (firstKey !== undefined) {
        this.delete(firstKey);
      }
    }
    super.set(key, value);
    return this;
  }
}

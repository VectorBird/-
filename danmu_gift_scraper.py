"""
弹幕和礼物捕获模块 - 独立的DOM scraping实现
从主框架中抽离出来，便于单独调试和测试
"""
import hashlib
import sys
from typing import Optional, Callable
from PyQt6.QtWebEngineCore import QWebEnginePage


class DanmuGiftScraper:
    """弹幕和礼物捕获器 - 使用DOM scraping方式"""
    
    def __init__(self, instance_id: str = "default"):
        """
        初始化捕获器
        
        Args:
            instance_id: 实例ID，用于区分不同的窗口实例
        """
        self.instance_id = instance_id
        self.instance_hash = hashlib.md5(instance_id.encode('utf-8')).hexdigest()[:8]
        
    def get_javascript_code(self) -> str:
        """
        获取JavaScript注入代码
        
        Returns:
            JavaScript代码字符串
        """
        js_code = rf"""
        (function() {{
            // 确保 sendToPy 函数存在且能正确发送数据
            if (!window.sendToPy) {{
                window.sendToPy = function(data) {{
                    try {{
                        // 方法1: 使用 webChannelTransport（推荐）
                        if (window.qt && window.qt.webChannelTransport) {{
                            window.qt.webChannelTransport.send(JSON.stringify({{
                                type: 6, id: Math.floor(Math.random() * 99999), 
                                object: "pyBridge", method: "post_danmu", args: [JSON.stringify(data)]
                            }}));
                            return;
                        }}
                        // 方法2: 如果 webChannelTransport 不存在，等待并重试
                        if (!window.sendToPyRetryCount) {{
                            window.sendToPyRetryCount = 0;
                        }}
                        if (window.sendToPyRetryCount < 10) {{
                            window.sendToPyRetryCount++;
                            setTimeout(() => {{
                                window.sendToPy(data);
                            }}, 100);
                            return;
                        }}
                        // 如果重试10次后仍然失败，输出错误（用于调试）
                        console.error("[sendToPy] webChannelTransport 不可用，数据发送失败:", data);
                    }} catch (e) {{
                        console.error("[sendToPy] 发送数据时出错:", e, "数据:", data);
                    }}
                }};
            }}
            
            // 使用唯一标识符避免多个窗口之间的JavaScript冲突
            const instanceId = "{self.instance_hash}";
            const activeFlag = "v64_dom_active_" + instanceId;
            if (window[activeFlag]) return;
            window[activeFlag] = true;
            
            // 等待 webChannelTransport 初始化（最多等待3秒）
            let initAttempts = 0;
            const maxInitAttempts = 30; // 30次 * 100ms = 3秒
            const checkWebChannel = setInterval(() => {{
                initAttempts++;
                if (window.qt && window.qt.webChannelTransport) {{
                    clearInterval(checkWebChannel);
                    console.log("[DOM扫描器] webChannelTransport 已就绪，开始扫描");
                }} else if (initAttempts >= maxInitAttempts) {{
                    clearInterval(checkWebChannel);
                    console.warn("[DOM扫描器] webChannelTransport 初始化超时，但将继续尝试扫描");
                }}
            }}, 100);
            
            // 弹幕缓存（使用实例ID确保每个窗口独立）
            const cachePrefix = "idxCache_" + instanceId;
            if (!window[cachePrefix]) window[cachePrefix] = new Set();
            const idxCache = window[cachePrefix];
            
            // 在线人数缓存（避免频繁更新）
            let lastViewerCount = '';
            let viewerCountUpdateTime = 0;
            
            // 检测回复框状态（用户是否已登录）
            function checkReplyBox() {{
                const ed = document.querySelector('[data-slate-editor="true"]') || 
                          document.querySelector('.ace-line')?.parentElement ||
                          document.querySelector('textarea[placeholder*="说点什么"]') ||
                          document.querySelector('textarea[placeholder*="发送"]');
                const detected = ed !== null && ed !== undefined;
                // 只在状态变化时发送通知（避免频繁发送）
                if (window.replyBoxDetected !== detected) {{
                    window.replyBoxDetected = detected;
                    window.sendToPy({{type: 'reply_box_detected', detected: detected}});
                }}
            }}
            
            // 立即检查一次，然后定期检查（每3秒检查一次）
            checkReplyBox();
            setInterval(checkReplyBox, 3000);
            
            // 礼物缓存（使用实例ID确保每个窗口独立）
            const giftCachePrefix = "giftCache_" + instanceId;
            if (!window[giftCachePrefix]) window[giftCachePrefix] = new Set();
            const giftCache = window[giftCachePrefix];
            
            // 礼物容器区域监控缓存（用于监控礼物容器区域）
            const giftContainerCachePrefix = "giftContainerCache_" + instanceId;
            if (!window[giftContainerCachePrefix]) window[giftContainerCachePrefix] = new Set();
            const giftContainerCache = window[giftContainerCachePrefix];
            
            // 需要监控的关键词（粉丝团、灯牌、小心心）
            const giftKeywordsToMonitor = ['送粉丝团', '粉丝团', '灯牌', '小心心', '小心', '爱心'];
            
            // 礼物名称关键词映射（用于模糊匹配）
            if (!window.giftKeywords) {{
                window.giftKeywords = [
                    {{ keywords: ['人气', '票'], name: '人气票' }},
                    {{ keywords: ['粉丝', '团'], name: '粉丝团' }},
                    {{ keywords: ['小心', '心', '爱心'], name: '小心心' }},
                    {{ keywords: ['灯牌'], name: '灯牌' }},
                ];
            }}
            
            // 从图片周围的文本或DOM结构中识别礼物名称（模糊匹配）
            function getGiftNameFromNode(node) {{
                const allText = node.innerText || node.textContent || '';
                
                // 支持"送出了"和"送出"两种格式
                let parts = allText.split('送出了');
                if (parts.length < 2) {{
                    parts = allText.split('送出');
                    if (parts.length < 2) return null;
                }}
                
                let giftText = parts[1].trim();
                if (giftText) {{
                    // 移除数量信息（x1、x 1、×1等）
                    giftText = giftText.replace(/\d+\s*[个xX×]/g, '').replace(/[x×X]\s*\d+/g, '').replace(/^\d+\s*/, '').trim();
                }}
                
                if (!giftText) return null;
                
                // 方法1: 尝试匹配已知礼物关键词
                for (let kw of window.giftKeywords) {{
                    const matchedKeywords = kw.keywords.filter(k => giftText.includes(k));
                    if (matchedKeywords.length >= Math.ceil(kw.keywords.length / 2)) {{
                        return kw.name;
                    }}
                }}
                
                // 方法2: 尝试从图片后面的span元素中提取
                const img = node.querySelector('img.OE081ZUF, img[class*="OE081ZUF"], img');
                if (img) {{
                    let nextSibling = img.nextElementSibling;
                    let foundText = '';
                    let tries = 0;
                    while (nextSibling && !foundText && tries < 5) {{
                        const siblingText = (nextSibling.innerText || nextSibling.textContent || '').trim();
                        if (siblingText && siblingText.length > 0 && !siblingText.match(/^\\d+$/) && !siblingText.match(/^[x×X]$/)) {{
                            foundText = siblingText.replace(/[x×X]\\s*\\d+/g, '').trim();
                        }}
                        nextSibling = nextSibling.nextElementSibling;
                        tries++;
                    }}
                    
                    if (foundText) {{
                        for (let kw of window.giftKeywords) {{
                            const matchedKeywords = kw.keywords.filter(k => foundText.includes(k));
                            if (matchedKeywords.length >= Math.ceil(kw.keywords.length / 2)) {{
                                return kw.name;
                            }}
                        }}
                        return foundText.replace(/\d+/g, '').trim() || null;
                    }}
                }}
                
                // 方法3: 从giftText中提取第一个有意义的词（直接返回，支持任意礼物名称）
                if (giftText) {{
                    const words = giftText.split(/[\\s\\n\\r\\u3000]+/).filter(w => {{
                        return w.length > 0 && !w.match(/^\\d+$/) && !w.match(/^[x×X]$/);
                    }});
                    
                    if (words.length > 0) {{
                        const firstWord = words[0];
                        // 先尝试匹配已知关键词
                        for (let kw of window.giftKeywords) {{
                            const matchedKeywords = kw.keywords.filter(k => firstWord.includes(k) || giftText.includes(k));
                            if (matchedKeywords.length >= Math.ceil(kw.keywords.length / 2)) {{
                                return kw.name;
                            }}
                        }}
                        // 如果没有匹配到，直接返回第一个词（支持任意礼物名称，如"大啤酒"、"棒棒糖"等）
                        return firstWord;
                    }}
                }}
                
                return null;
            }}
            
            // 检查是否是实时信息（非弹幕、非礼物）
            function isRealtimeInfo(text) {{
                const patterns = [
                    /加入了直播间/,
                    /分享了直播间/,
                    /成为了观众TOP/,
                    /为主播点了赞/,
                    /为主播点赞了/,
                    /点赞了/,
                    /为主播加了/,
                    /来了$/
                ];
                return patterns.some(pattern => pattern.test(text));
            }}
            
            // 检查是否是礼物信息
            function isGiftInfo(text) {{
                return text.includes('送出了') || text.includes('送出');
            }}
            
            // 扫描弹幕
            function scanDanmu() {{
                const nodes = document.querySelectorAll('div[data-index]');
                let foundCount = 0;
                let processedCount = 0;
                
                nodes.forEach(node => {{
                    foundCount++;
                    let idx = node.getAttribute('data-index');
                    if (!idx || idxCache.has(idx)) return;
                    
                    const nodeText = (node.innerText || node.textContent || '').trim();
                    
                    // 优先检查是否是礼物或实时信息，如果是则跳过（由专门的扫描函数处理）
                    if (isGiftInfo(nodeText)) return;
                    if (isRealtimeInfo(nodeText)) return;
                    
                    let spans = Array.from(node.querySelectorAll('span')).map(s => s.innerText.trim()).filter(s => s.length > 0);
                    
                    // 方法1: 如果有足够的span元素
                    if (spans.length >= 2) {{
                        let user = spans[0].replace('：','').replace('：','');
                        let contentNode = node.querySelector('[class*="ent-with-emoji-text"]');
                        let content = contentNode ? contentNode.innerText.trim() : spans[spans.length - 1];
                        
                        if (user && content && !content.includes('进入')) {{
                            idxCache.add(idx);
                            if(idxCache.size > 200) idxCache.delete(idxCache.values().next().value);
                            processedCount++;
                            window.sendToPy({{ type: 'danmu', user: user, content: content }});
                            return;
                        }}
                    }}
                    
                    // 方法2: 尝试从整个节点的文本中提取
                    if (nodeText && nodeText.length > 0 && nodeText.length < 500) {{
                        let match = nodeText.match(/^(.+?)[：:](.+)$/);
                        if (match && match[1] && match[2]) {{
                            let user = match[1].trim();
                            let content = match[2].trim();
                            
                            if (user && content && !content.includes('进入') && user.length < 50) {{
                                idxCache.add(idx);
                                if(idxCache.size > 200) idxCache.delete(idxCache.values().next().value);
                                processedCount++;
                                window.sendToPy({{ type: 'danmu', user: user, content: content }});
                                return;
                            }}
                        }}
                    }}
                }});
            }}
            
            // 扫描实时信息（加入了直播间、分享了直播间等）
            function scanRealtimeInfo() {{
                // 方法1: 扫描所有带data-index的div
                const nodes1 = document.querySelectorAll('div[data-index]');
                scanRealtimeInfoFromNodes(nodes1, 'data-index-div');
                
                // 方法2: 扫描所有div元素（不限于data-index）
                const allDivs = document.querySelectorAll('div');
                const realtimeDivs = Array.from(allDivs).filter(div => {{
                    const text = div.innerText || div.textContent || '';
                    return isRealtimeInfo(text) && !div.hasAttribute('data-index');
                }});
                scanRealtimeInfoFromNodes(realtimeDivs, 'realtime-div');
            }}
            
            function scanRealtimeInfoFromNodes(nodes, sourceType) {{
                const realtimeCachePrefix = "realtimeCache_" + instanceId;
                if (!window[realtimeCachePrefix]) window[realtimeCachePrefix] = new Set();
                const realtimeCache = window[realtimeCachePrefix];
                
                nodes.forEach(node => {{
                    // 生成唯一标识
                    let uniqueId = '';
                    if (node.hasAttribute('data-index')) {{
                        uniqueId = 'data-index-' + node.getAttribute('data-index');
                    }} else {{
                        // 使用元素在DOM中的位置作为标识
                        const path = [];
                        let current = node;
                        while (current && current !== document.body) {{
                            const parent = current.parentElement;
                            if (parent) {{
                                const index = Array.from(parent.children).indexOf(current);
                                path.unshift(index);
                            }}
                            current = parent;
                        }}
                        uniqueId = sourceType + '-' + path.join('-');
                    }}
                    
                    if (realtimeCache.has(uniqueId)) return;
                    
                    const allText = node.innerText || node.textContent || '';
                    
                    if (isRealtimeInfo(allText)) {{
                        let spans = Array.from(node.querySelectorAll('span')).map(s => s.innerText.trim()).filter(t => t.length > 0);
                        let user = '';
                        
                        // 提取用户名（从文本中提取，支持多种格式）
                        if (spans.length > 0) {{
                            user = spans[0].replace('：', '').replace(':', '').trim();
                        }}
                        
                        // 如果span中没有用户名，尝试从文本中提取
                        if (!user) {{
                            // 格式1: "用户名：为主播点赞了"
                            const match1 = allText.match(/^([^：:]+)[：:]/);
                            if (match1) {{
                                user = match1[1].trim();
                            }} else {{
                                // 格式2: "用户名加入了直播间"
                                const match2 = allText.match(/^([^加]+)加入了直播间/);
                                if (match2) {{
                                    user = match2[1].trim();
                                }}
                            }}
                        }}
                        
                        let infoType = 'other';
                        let infoContent = allText;
                        
                        if (allText.includes('加入了直播间')) {{
                            infoType = 'enter';
                            if (!user) {{
                                const enterMatch = allText.match(/^([^加]+)加入了直播间/);
                                if (enterMatch) {{
                                    user = enterMatch[1].trim();
                                }}
                            }}
                            infoContent = '';
                        }} else if (allText.includes('分享了直播间')) {{
                            infoType = 'share';
                            infoContent = '';
                        }} else if (allText.includes('成为了观众TOP')) {{
                            infoType = 'top';
                            infoContent = '';
                        }} else if (allText.includes('为主播点了赞') || allText.includes('为主播点赞了') || allText.includes('点赞了')) {{
                            infoType = 'like';
                            if (!user) {{
                                const likeMatch = allText.match(/^([^：:]+)[：:]/);
                                if (likeMatch) {{
                                    user = likeMatch[1].trim();
                                }}
                            }}
                            infoContent = '';
                        }} else if (allText.includes('为主播加了')) {{
                            infoType = 'score';
                            if (!user) {{
                                const scoreMatch = allText.match(/^([^为]+)为主播加了/);
                                if (scoreMatch) {{
                                    user = scoreMatch[1].trim();
                                }}
                            }}
                            const scoreMatch = allText.match(/(\\d+)\\s*分/);
                            if (scoreMatch) {{
                                infoContent = scoreMatch[1] + '分';
                            }} else {{
                                infoContent = '';
                            }}
                        }} else if (allText.endsWith('来了')) {{
                            infoType = 'enter';
                            if (!user) {{
                                const comeMatch = allText.match(/^([^来]+)来了$/);
                                if (comeMatch) {{
                                    user = comeMatch[1].trim();
                                }}
                            }}
                            infoContent = '';
                        }}
                        
                        // 检查是否包含页面结构关键词（这些不应该被捕获为实时信息）
                        const pageStructureKeywords = ['在线观众', '全部', '高等级用户', '1000贡献用户', '需先登录', '本场点赞', '关注', '小时榜', '人气榜'];
                        if (pageStructureKeywords.some(keyword => allText.includes(keyword))) {{
                            return;
                        }}
                        
                        // 检查是否包含多个弹幕（通过统计"："的数量来判断）
                        const danmuMatches = allText.match(/[^：:]+[：:]/g);
                        if (danmuMatches && danmuMatches.length > 1) {{
                            return;
                        }}
                        
                        // 使用文本内容作为唯一标识的一部分，避免重复捕获相同内容
                        const contentKey = infoType + '-' + (user || '');
                        if (realtimeCache.has(contentKey)) return;
                        
                        if (user || infoContent) {{
                            realtimeCache.add(uniqueId);
                            realtimeCache.add(contentKey);
                            if (realtimeCache.size > 500) {{
                                const firstKey = realtimeCache.values().next().value;
                                realtimeCache.delete(firstKey);
                            }}
                            window.sendToPy({{type: 'realtime_info', info_type: infoType, user: user, content: infoContent}});
                        }}
                    }}
                }});
            }}
            
            // 扫描礼物（弹幕区域的礼物）
            function scanGifts() {{
                const nodes = document.querySelectorAll('div[data-index]');
                let foundCount = 0;
                let processedCount = 0;
                
                nodes.forEach(node => {{
                    const allText = node.innerText || node.textContent || '';
                    if (!allText.includes('送出了') && !allText.includes('送出')) return;
                    
                    foundCount++;
                    let idx = node.getAttribute('data-index');
                    if (!idx || giftCache.has(idx)) return;
                    
                    let user = '';
                    let giftName = '';
                    let giftCount = '1';
                    
                    // 提取用户（支持"送出了"和"送出"两种格式）
                    const userMatch = allText.match(/(.+?)\\s*(?:送出了|送出)/);
                    if (userMatch) {{
                        user = userMatch[1].trim();
                    }}
                    
                    // 提取礼物名称
                    giftName = getGiftNameFromNode(node);
                    
                    // 提取数量（支持多种格式：x1、x 1、×1、× 1等）
                    const countMatch = allText.match(/[x×X]\\s*(\\d+)|送出了\\s*(\\d+)|送出\\s*(\\d+)/);
                    if (countMatch) {{
                        giftCount = (countMatch[1] || countMatch[2] || countMatch[3] || '1').toString();
                    }}
                    
                    if (user && giftName) {{
                        giftCache.add(idx);
                        if(giftCache.size > 200) giftCache.delete(giftCache.values().next().value);
                        processedCount++;
                        window.sendToPy({{ type: 'gift', user: user, gift_name: giftName, gift_count: giftCount }});
                    }}
                }});
            }}
            
            // 扫描直播画面左下角的用户列表区域（明文礼物信息）- 重要来源
            // 礼物去重缓存（使用内容+时间戳，防止重复捕获）
            const giftContentCachePrefix = "giftContentCache_" + instanceId;
            if (!window[giftContentCachePrefix]) window[giftContentCachePrefix] = new Map();
            const giftContentCache = window[giftContentCachePrefix];
            const GIFT_CACHE_TTL = 60000; // 60秒内相同内容不重复捕获
            
            function scanLeftBottomUserList() {{
                try {{
                    // 查找所有可能包含礼物信息的元素
                    const allElements = document.querySelectorAll('div, span, p');
                    let domSelectorChecked = 0;
                    let domSelectorMatched = 0;
                    const domSelectorGifts = [];
                    
                    allElements.forEach(el => {{
                        const text = (el.innerText || el.textContent || '').trim();
                        if (!text || text.length < 3) return;
                        
                        // 检查是否包含"送"关键词
                        if (!text.includes('送')) return;
                        
                        domSelectorChecked++;
                        
                        // 检查元素位置（左下角区域）
                        const rect = el.getBoundingClientRect();
                        const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
                        const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
                        
                        // 判断是否在左下角区域（放宽条件）
                        const isLeftSide = rect.left < viewportWidth * 0.5;
                        const isBottomArea = rect.top > viewportHeight * 0.3;
                        const isLeftArea = rect.left < viewportWidth * 0.6;
                        const isShortGiftText = text.length < 100;
                        const isZeroPosition = rect.left === 0 && rect.top === 0;
                        
                        if (isLeftSide || isLeftArea || isShortGiftText || isZeroPosition) {{
                            // 使用关键词匹配方式提取礼物信息
                            // 所有礼物名称列表（包括粉丝团和灯牌，按长度从长到短排序，优先匹配长名称）
                            const giftKeywords = [
                                '点亮粉丝团', '粉丝团灯牌', '浪漫雪绘', '为你闪耀',
                                '粉丝团', '灯牌', '玫瑰', '小心心', '棒棒糖', '鲜花', '亲吻', 'Thuglife', '礼花筒', '真的爱你',
                                '浪漫花火', '抖音1号', '红包', '冬雪之爱', '冰封誓约', '雪落生花', '萌狐戏雪',
                                '星愿雪淞', '冰雪城堡', '日照金山', '跑车', '热气球', '比心兔兔', '抖音飞艇',
                                '豪华邮轮', '云中秘境', 'PK宝箱', '万象烟花', '人气票', '真爱玫瑰',
                                '一束花开', '闪耀星辰', '浪漫恋人', '一路有你', '浪漫马车', '梦幻城堡',
                                '掌上明珠', '为爱启航', '花落长亭', '星际玫瑰', '海上生明月', '捏捏小脸',
                                '天空之镜', '花海泛舟', '真爱永恒', '情定三生', '梦幻蝶翼', '天使之翼',
                                '暗夜之翼', '大圣抢亲', '闪光舞台', '豪华蛋糕', '胡萝卜', '随机舞蹈',
                                '魔法镜', '逗兔棒', '游戏手柄', '拯救爱播', '摩天大厦', '环游世界',
                                '雪绒花', '火龙爆发', '荧光棒', '光之祝福', '奇幻八音盒', '龙抬头',
                                '为你举牌', '爱情树下', '星星点灯', '纸短情长', '云霄大厦', '月下瀑布',
                                '黄桃罐头', '蝶・连理枝', '趣玩泡泡', '蜜蜂叮叮', '灵龙现世', '奏响人生',
                                '永生花', 'ONE礼挑一', '冰冻战车', '炫彩射击', '拳拳出击', '爱的纸鹤',
                                '爱你哟', '大啤酒', '直升机', '嘉年华', '比心', '加油鸭', '送你花花',
                                '你最好看', '抖音', '私人飞机'
                            ];
                            
                            // 页面结构关键词（用于过滤）
                            const pageStructureKeywords = ['潇洒哥', '无畏契约', '本场点赞', '关注', '小时榜', '人气榜', '自动', '直播加载中', 'G', '100+', '万', '重庆第', '名'];
                            
                            // 查找所有"送"字的位置
                            const sendIndexes = [];
                            for (let i = 0; i < text.length; i++) {{
                                if (text[i] === '送' || (i < text.length - 1 && text.substring(i, i + 2) === '送')) {{
                                    sendIndexes.push(i);
                                }}
                            }}
                            
                            // 对每个"送"字，尝试提取礼物信息
                            sendIndexes.forEach(sendIndex => {{
                                // 提取"送"之前的文本作为潜在用户名
                                const beforeSend = text.substring(0, sendIndex).trim();
                                // 提取"送"之后的文本
                                const afterSend = text.substring(sendIndex + 1).trim();
                                
                                // 查找礼物名称（在"送"之后，优先匹配长名称）
                                let foundGift = null;
                                let giftStartIndex = -1;
                                let giftEndIndex = -1;
                                
                                for (const giftKeyword of giftKeywords) {{
                                    const index = afterSend.indexOf(giftKeyword);
                                    if (index >= 0 && index < 100) {{ // 礼物名称应该在"送"之后100字符内
                                        foundGift = giftKeyword;
                                        giftStartIndex = index;
                                        giftEndIndex = index + giftKeyword.length;
                                        break;
                                    }}
                                }}
                                
                                if (foundGift) {{
                                    // 提取用户名（"送"之前的最后一行或最后一段）
                                    let user = beforeSend;
                                    // 如果包含换行，取最后一行
                                    const lastNewlineIndex = user.lastIndexOf('\\n');
                                    if (lastNewlineIndex >= 0) {{
                                        user = user.substring(lastNewlineIndex + 1).trim();
                                    }}
                                    // 如果用户名太长，可能是页面结构，跳过
                                    if (user.length > 50) {{
                                        return;
                                    }}
                                    
                                    // 提取数量（在礼物名称之后查找 x/×/X + 数字）
                                    const afterGift = afterSend.substring(giftEndIndex);
                                    const countMatch = afterGift.match(/[x×X]\\s*(\\d+)/);
                                    const giftCount = countMatch ? countMatch[1] : '1';
                                    
                                    // 验证用户名不是页面结构关键词
                                    const isPageStructure = pageStructureKeywords.some(keyword => 
                                        user.includes(keyword) || user === keyword
                                    );
                                    
                                    // 基本验证
                                    if (user.length > 0 && 
                                        user.length <= 50 &&
                                        !isPageStructure &&
                                        user !== '自动' && user !== '直播加载中' &&
                                        !/^\\d+$/.test(user)) {{
                                        domSelectorMatched++;
                                        domSelectorGifts.push({{
                                            user: user,
                                            giftName: foundGift,
                                            giftCount: giftCount,
                                            element: el,
                                            text: text.substring(0, 100),
                                            method: 'keyword_match',
                                            position: 'left:' + Math.floor(rect.left) + ' top:' + Math.floor(rect.top)
                                        }});
                                    }}
                                }}
                            }});
                        }}
                    }});
                    
                    // 如果通过DOM选择器找到了礼物信息，优先使用
                    if (domSelectorGifts.length > 0) {{
                        // 去重和排序：使用用户+礼物名+数量作为唯一标识
                        const uniqueGifts = new Map();
                        const giftTimestamps = new Map();
                        domSelectorGifts.forEach((gift, index) => {{
                            const key = gift.user + '|' + gift.giftName + '|' + gift.giftCount;
                            // 如果已经存在，保留最新的（索引更大的）
                            if (!uniqueGifts.has(key) || (giftTimestamps.get(key) || 0) < index) {{
                                uniqueGifts.set(key, gift);
                                giftTimestamps.set(key, index);
                            }}
                        }});
                        
                        // 转换为数组并排序（按时间戳降序，最新的在前）
                        const sortedGifts = Array.from(uniqueGifts.values()).sort((a, b) => {{
                            const keyA = a.user + '|' + a.giftName + '|' + a.giftCount;
                            const keyB = b.user + '|' + b.giftName + '|' + b.giftCount;
                            return (giftTimestamps.get(keyB) || 0) - (giftTimestamps.get(keyA) || 0);
                        }});
                        
                        // 发送找到的礼物信息（同一用户送同一礼物时累加数量）
                        const newGifts = [];
                        const now = Date.now();
                        
                        sortedGifts.forEach(gift => {{
                            // 使用 user|giftName 作为key（不包括数量），用于识别同一用户送同一礼物
                            const userGiftKey = gift.user + '|' + gift.giftName;
                            // 使用完整的礼物信息（包括数量）作为唯一标识，避免重复处理同一条礼物信息
                            const giftTextKey = gift.user + '|' + gift.giftName + '|' + gift.giftCount + '|' + (gift.text || '').substring(0, 50);
                            const cachedData = giftContentCache.get(userGiftKey);
                            
                            // 检查是否已经处理过这条完全相同的礼物信息（防止重复扫描导致自增）
                            if (cachedData && cachedData.lastProcessedText === giftTextKey) {{
                                // 这是同一条礼物信息，已经处理过，跳过
                                return;
                            }}
                            
                            if (cachedData) {{
                                // 如果缓存中存在，检查是否在缓存期内
                                const {{timestamp, count, lastProcessedText}} = cachedData;
                                if ((now - timestamp) < GIFT_CACHE_TTL) {{
                                    // 在缓存期内，且礼物信息有变化（数量增加），才累加数量
                                    const currentCount = parseInt(gift.giftCount || 1);
                                    const cachedCount = parseInt(count || 1);
                                    
                                    // 只有当新检测到的数量大于缓存的数量时，才认为是新礼物并累加
                                    if (currentCount > cachedCount) {{
                                        // 数量增加了，累加增量
                                        const increment = currentCount - cachedCount;
                                        const newCount = cachedCount + increment;
                                        // 更新缓存：更新数量、时间戳和最后处理的文本
                                        giftContentCache.set(userGiftKey, {{
                                            timestamp: now, 
                                            count: newCount,
                                            lastProcessedText: giftTextKey
                                        }});
                                        
                                        // 发送更新后的礼物信息（累加数量）
                                        const displayText = gift.user + ' 送 ' + gift.giftName + (newCount !== 1 ? ' ×' + newCount : '');
                                        window.sendToPy({{
                                            type: 'gift',
                                            user: gift.user,
                                            gift_name: gift.giftName,
                                            gift_count: newCount,
                                            source: 'left_bottom_user_list',
                                            method: gift.method || 'keyword_match',
                                            display_text: displayText,
                                            is_update: true  // 标记为更新，不是新礼物
                                        }});
                                    }} else {{
                                        // 数量没有增加，只是重复扫描，更新最后处理的文本但不发送消息
                                        giftContentCache.set(userGiftKey, {{
                                            timestamp: timestamp,  // 保持原时间戳
                                            count: cachedCount,     // 保持原数量
                                            lastProcessedText: giftTextKey  // 更新最后处理的文本
                                        }});
                                    }}
                                    return;
                                }}
                            }}
                            
                            // 新礼物或缓存已过期，创建新记录
                            giftContentCache.set(userGiftKey, {{
                                timestamp: now, 
                                count: parseInt(gift.giftCount || 1),
                                lastProcessedText: giftTextKey
                            }});
                            newGifts.push(gift);
                        }});
                        
                        // 只输出新捕获的礼物信息（避免重复输出）
                        if (newGifts.length > 0) {{
                            // 发送新捕获的礼物信息（定义为礼物消息）
                            newGifts.forEach(gift => {{
                                const displayText = gift.user + ' 送 ' + gift.giftName + (gift.giftCount && gift.giftCount !== '1' ? ' ×' + gift.giftCount : '');
                                
                                // 发送礼物信息（定义为礼物消息）
                                window.sendToPy({{
                                    type: 'gift',
                                    user: gift.user,
                                    gift_name: gift.giftName,
                                    gift_count: gift.giftCount,
                                    source: 'left_bottom_user_list',
                                    method: gift.method || 'keyword_match',
                                    display_text: displayText,
                                    is_update: false  // 标记为新礼物
                                }});
                            }});
                        }}
                        
                        // 清理过期的缓存（避免内存泄漏）
                        if (giftContentCache.size > 500) {{
                            for (let [key, data] of giftContentCache.entries()) {{
                                const timestamp = (typeof data === 'object' && data.timestamp) ? data.timestamp : data;
                                if (now - timestamp > GIFT_CACHE_TTL * 2) {{ // 清理超过2倍缓存时间的条目
                                    giftContentCache.delete(key);
                                }}
                            }}
                        }}
                    }}
                }} catch (e) {{
                    // 静默处理错误，避免影响其他功能
                }}
            }}
            
            // 在线人数和点赞数缓存
            let lastLikeCount = '';
            let likeCountUpdateTime = 0;
            
            // 扫描在线人数和点赞数
            function scanViewerCount() {{
                // 扫描在线人数
                const viewerCountEl = document.querySelector('div[data-e2e="live-room-audience"]');
                if (viewerCountEl) {{
                    let count = viewerCountEl.innerText.trim();
                    const now = Date.now();
                    if (count !== lastViewerCount && (now - viewerCountUpdateTime > 5000)) {{
                        lastViewerCount = count;
                        viewerCountUpdateTime = now;
                        window.sendToPy({{ type: 'viewer_count', viewer_count: count }});
                    }}
                }}
                
                // 扫描点赞数（本场点赞）
                // 注意：不能使用 :contains() 选择器（不是有效的CSS选择器）
                // 先尝试通过属性选择器查找
                let likeCountEl = document.querySelector('[data-e2e="live-room-like-count"]') || 
                                 document.querySelector('.like-count');
                
                if (!likeCountEl) {{
                    // 通过文本查找包含"本场点赞"的元素
                    const allDivs = document.querySelectorAll('div');
                    for (let div of allDivs) {{
                        const text = div.innerText || div.textContent || '';
                        if (text.includes('本场点赞') && text.match(/\\d+[万千]?/)) {{
                            // 提取点赞数（格式：数字.数字万本场点赞 或 数字万本场点赞）
                            const match = text.match(/(\\d+\\.?\\d*)[万千]?本场点赞/);
                            if (match) {{
                                let likeCount = match[1] + (text.includes('万') ? '万' : '');
                                const now = Date.now();
                                if (likeCount !== lastLikeCount && (now - likeCountUpdateTime > 5000)) {{
                                    lastLikeCount = likeCount;
                                    likeCountUpdateTime = now;
                                    window.sendToPy({{ type: 'like_count', like_count: likeCount }});
                                }}
                            }}
                            break;
                        }}
                    }}
                }} else {{
                    let likeCount = likeCountEl.innerText.trim();
                    const now = Date.now();
                    if (likeCount !== lastLikeCount && (now - likeCountUpdateTime > 5000)) {{
                        lastLikeCount = likeCount;
                        likeCountUpdateTime = now;
                        window.sendToPy({{ type: 'like_count', like_count: likeCount }});
                    }}
                }}
            }}
            
            // 主扫描函数
            function scan() {{
                scanGifts();  // 先扫描礼物（优先级最高）
                scanLeftBottomUserList();  // 扫描左下角用户列表区域（重要来源）
                scanRealtimeInfo();  // 再扫描实时信息
                scanDanmu();  // 最后扫描弹幕（排除礼物和实时信息）
                scanViewerCount();
            }}
            
            // 立即执行一次扫描
            scan();
            
            // 定期扫描（每1秒扫描一次）
            setInterval(scan, 1000);
            
            console.log(">>> [DOM扫描器] 已就绪，实例ID: " + instanceId);
        }})();
        """
        return js_code
    
    def inject(self, page: QWebEnginePage) -> bool:
        """
        将JavaScript代码注入到页面中
        
        Args:
            page: QWebEnginePage对象
            
        Returns:
            成功返回True，失败返回False
        """
        try:
            # 检查页面是否有效
            if not page:
                return False
            
            # 检查页面URL是否有效
            url = page.url().toString()
            if not url or url == 'about:blank':
                return False
            
            # 获取JavaScript代码
            js_code = self.get_javascript_code()
            
            # 注入JavaScript代码（延迟注入，确保页面完全加载和webChannelTransport已初始化）
            # 使用 setTimeout 确保在页面完全加载后执行
            full_js_code = f"""
            (function() {{
                function injectCode() {{
                    {js_code}
                }}
                
                // 如果页面已加载完成，立即执行
                if (document.readyState === 'complete' || document.readyState === 'interactive') {{
                    // 等待 webChannelTransport 初始化（最多等待2秒）
                    let attempts = 0;
                    const maxAttempts = 20;
                    const checkInterval = setInterval(() => {{
                        attempts++;
                        if (window.qt && window.qt.webChannelTransport) {{
                            clearInterval(checkInterval);
                            injectCode();
                        }} else if (attempts >= maxAttempts) {{
                            clearInterval(checkInterval);
                            // 即使 webChannelTransport 未初始化，也尝试注入（sendToPy 会重试）
                            injectCode();
                        }}
                    }}, 100);
                }} else {{
                    // 如果页面未加载完成，等待 DOMContentLoaded
                    window.addEventListener('DOMContentLoaded', function() {{
                        let attempts = 0;
                        const maxAttempts = 20;
                        const checkInterval = setInterval(() => {{
                            attempts++;
                            if (window.qt && window.qt.webChannelTransport) {{
                                clearInterval(checkInterval);
                                injectCode();
                            }} else if (attempts >= maxAttempts) {{
                                clearInterval(checkInterval);
                                injectCode();
                            }}
                        }}, 100);
                    }});
                }}
            }})();
            """
            
            page.runJavaScript(full_js_code)
            return True
            
        except Exception as e:
            import traceback
            error_msg = f"JavaScript注入失败: {type(e).__name__}: {e}\n\n{traceback.format_exc()}"
            print(f"[DanmuGiftScraper] 错误: {error_msg}")
            sys.stdout.flush()
            return False

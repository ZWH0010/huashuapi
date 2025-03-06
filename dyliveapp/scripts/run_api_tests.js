const newman = require('newman');
const path = require('path');
const fs = require('fs');
const moment = require('moment');

// 配置
const config = {
    collection: path.join(__dirname, '../docs/postman/DyLiveApp.postman_collection.json'),
    environment: path.join(__dirname, '../docs/postman/DyLiveApp.postman_environment.json'),
    reporters: ['cli', 'htmlextra', 'json'],
    reporter: {
        htmlextra: {
            export: path.join(__dirname, `../test-reports/report-${moment().format('YYYY-MM-DD-HH-mm-ss')}.html`),
            template: 'default',
            title: 'DyLiveApp API Test Report',
            browserTitle: "DyLiveApp API Tests",
            showEnvironmentData: true,
            showGlobalData: true,
            showMarkdownLinks: true,
            showFolderDescription: true,
            timezone: "Asia/Shanghai"
        },
        json: {
            export: path.join(__dirname, `../test-reports/report-${moment().format('YYYY-MM-DD-HH-mm-ss')}.json`)
        }
    }
};

// 创建报告目录
if (!fs.existsSync(path.join(__dirname, '../test-reports'))) {
    fs.mkdirSync(path.join(__dirname, '../test-reports'));
}

// 运行测试
newman.run({
    collection: require(config.collection),
    environment: require(config.environment),
    reporters: config.reporters,
    reporter: config.reporter,
    iterationCount: 1,
    bail: true, // 遇到错误时停止
    timeoutRequest: 5000, // 请求超时时间（毫秒）
    delayRequest: 100 // 请求间隔（毫秒）
}, function (err, summary) {
    if (err) {
        console.error('运行测试时发生错误:', err);
        process.exit(1);
    }

    // 生成测试摘要
    const results = {
        total: summary.run.stats.requests.total,
        failed: summary.run.stats.requests.failed,
        passed: summary.run.stats.assertions.total - summary.run.stats.assertions.failed,
        failedAssertions: summary.run.stats.assertions.failed,
        totalTime: summary.run.timings.completed - summary.run.timings.started,
        avgResponseTime: summary.run.timings.responseAverage,
        timestamp: moment().format('YYYY-MM-DD HH:mm:ss')
    };

    // 将摘要写入文件
    fs.writeFileSync(
        path.join(__dirname, `../test-reports/summary-${moment().format('YYYY-MM-DD-HH-mm-ss')}.json`),
        JSON.stringify(results, null, 2)
    );

    // 输出结果
    console.log('\n测试完成！');
    console.log('总请求数:', results.total);
    console.log('失败请求:', results.failed);
    console.log('通过断言:', results.passed);
    console.log('失败断言:', results.failedAssertions);
    console.log('总耗时:', results.totalTime, 'ms');
    console.log('平均响应时间:', results.avgResponseTime, 'ms');

    // 如果有失败的测试，退出码设为1
    if (results.failed > 0 || results.failedAssertions > 0) {
        process.exit(1);
    }
}); 
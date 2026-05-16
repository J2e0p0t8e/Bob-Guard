// Bob-Guard Frontend JavaScript

// Global state
let currentAnalysisResults = null;
let currentViolations = [];

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    initializeTabs();
    initializeFileUpload();
    initializeAnalyzeButton();
    initializeFilters();
});

// Tab functionality
function initializeTabs() {
    const tabButtons = document.querySelectorAll('.tab-button');
    const tabContents = document.querySelectorAll('.tab-content');

    tabButtons.forEach(button => {
        button.addEventListener('click', function() {
            const tabId = this.getAttribute('data-tab');
            
            // Remove active class from all tabs
            tabButtons.forEach(btn => btn.classList.remove('active'));
            tabContents.forEach(content => content.classList.remove('active'));
            
            // Add active class to clicked tab
            this.classList.add('active');
            document.getElementById(tabId).classList.add('active');
        });
    });
}

// File upload functionality
function initializeFileUpload() {
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');
    const fileList = document.getElementById('fileList');

    if (!dropZone || !fileInput) return;

    // Drag and drop events
    dropZone.addEventListener('dragover', function(e) {
        e.preventDefault();
        this.classList.add('drag-over');
    });

    dropZone.addEventListener('dragleave', function(e) {
        e.preventDefault();
        this.classList.remove('drag-over');
    });

    dropZone.addEventListener('drop', function(e) {
        e.preventDefault();
        this.classList.remove('drag-over');
        
        const files = e.dataTransfer.files;
        handleFiles(files);
    });

    // File input change
    fileInput.addEventListener('change', function(e) {
        handleFiles(this.files);
    });

    function handleFiles(files) {
        fileList.innerHTML = '';
        
        Array.from(files).forEach(file => {
            const fileItem = document.createElement('div');
            fileItem.className = 'file-item';
            fileItem.innerHTML = `
                <span>📄 ${file.name}</span>
                <button class="btn btn-small btn-primary" onclick="analyzeFile('${file.name}')">
                    Analyze
                </button>
            `;
            fileList.appendChild(fileItem);
        });
    }
}

// Analyze repository button
function initializeAnalyzeButton() {
    const analyzeBtn = document.getElementById('analyzeRepoBtn');
    if (!analyzeBtn) return;

    analyzeBtn.addEventListener('click', function() {
        const repoPath = document.getElementById('repoPathInput').value.trim();
        const autoFix = document.getElementById('autoFixCheckbox').checked;
        const generateTests = document.getElementById('generateTestsCheckbox').checked;

        if (!repoPath) {
            showNotification('Please enter a repository path', 'error');
            return;
        }

        analyzeRepository(repoPath, autoFix, generateTests);
    });
}

// Analyze repository
async function analyzeRepository(repoPath, autoFix, generateTests) {
    showProgress('Analyzing repository...');

    try {
        const response = await fetch('/api/analyze', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                repo_path: repoPath
            })
        });

        const data = await response.json();

        if (data.success) {
            currentAnalysisResults = data;
            currentViolations = data.violations || [];
            
            // Store in session storage
            sessionStorage.setItem('analysisResults', JSON.stringify(data));
            
            hideProgress();
            displayResults(data);
            
            showNotification('Analysis complete!', 'success');

            // Auto-remediate if requested
            if (autoFix && data.violations.length > 0) {
                await remediateViolations(data.violations, true);
            }
        } else {
            hideProgress();
            showNotification(data.error || 'Analysis failed', 'error');
        }
    } catch (error) {
        hideProgress();
        showNotification('Error connecting to server', 'error');
        console.error('Analysis error:', error);
    }
}

// Analyze single file
async function analyzeFile(filename) {
    showNotification('Analyzing file...', 'info');
    
    // Implementation for single file analysis
    console.log('Analyzing file:', filename);
}

// Display results
function displayResults(data) {
    const resultsSection = document.getElementById('resultsSection');
    if (!resultsSection) return;

    resultsSection.style.display = 'block';

    // Update summary cards
    document.getElementById('totalViolations').textContent = data.violations.length;
    
    const summary = data.summary || {};
    const bySeverity = summary.by_severity || {};
    
    document.getElementById('criticalCount').textContent = bySeverity.critical || 0;
    document.getElementById('highCount').textContent = bySeverity.high || 0;
    document.getElementById('mediumCount').textContent = bySeverity.medium || 0;
    document.getElementById('lowCount').textContent = bySeverity.low || 0;

    // Display top violations
    displayViolationsList(data.violations.slice(0, 5));

    // Setup action buttons
    setupActionButtons(data);
}

// Display violations list
function displayViolationsList(violations) {
    const violationsList = document.getElementById('violationsList');
    if (!violationsList) return;

    violationsList.innerHTML = '';

    violations.forEach(violation => {
        const item = document.createElement('div');
        item.className = `violation-item severity-${violation.severity.toLowerCase()}`;
        item.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: start;">
                <div>
                    <h4>${violation.rule_name}</h4>
                    <p><strong>File:</strong> ${violation.file_path} (Line ${violation.line_number})</p>
                    <p>${violation.description}</p>
                </div>
                <span class="severity-badge severity-${violation.severity.toLowerCase()}">
                    ${violation.severity}
                </span>
            </div>
        `;
        violationsList.appendChild(item);
    });
}

// Setup action buttons
function setupActionButtons(data) {
    const viewDetailsBtn = document.getElementById('viewDetailsBtn');
    const remediateBtn = document.getElementById('remediateBtn');
    const downloadReportBtn = document.getElementById('downloadReportBtn');

    if (viewDetailsBtn) {
        viewDetailsBtn.onclick = () => {
            sessionStorage.setItem('analysisResults', JSON.stringify(data));
            window.location.href = '/results';
        };
    }

    if (remediateBtn) {
        remediateBtn.onclick = () => {
            remediateViolations(data.violations, false);
        };
    }

    if (downloadReportBtn) {
        downloadReportBtn.onclick = () => {
            downloadReport(data.report_path);
        };
    }
}

// Remediate violations
async function remediateViolations(violations, autoApply) {
    if (!violations || violations.length === 0) {
        showNotification('No violations to remediate', 'info');
        return;
    }

    showProgress('Generating fixes...');

    try {
        const response = await fetch('/api/remediate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                violations: violations,
                auto_apply: autoApply,
                min_confidence: 0.7
            })
        });

        const data = await response.json();

        hideProgress();

        if (data.success) {
            showNotification(
                `Generated ${data.fixes_generated} fixes. Applied: ${data.fixes_applied}`,
                'success'
            );
        } else {
            showNotification(data.error || 'Remediation failed', 'error');
        }
    } catch (error) {
        hideProgress();
        showNotification('Error during remediation', 'error');
        console.error('Remediation error:', error);
    }
}

// Download report
function downloadReport(reportPath) {
    if (!reportPath) {
        showNotification('No report available', 'error');
        return;
    }

    const filename = reportPath.split('/').pop();
    window.location.href = `/api/reports/${filename}`;
}

// Progress indicator
function showProgress(message) {
    const progressSection = document.getElementById('progressSection');
    const progressText = document.getElementById('progressText');
    const progressFill = document.getElementById('progressFill');

    if (progressSection) {
        progressSection.style.display = 'block';
        progressText.textContent = message;
        
        // Animate progress bar
        let progress = 0;
        const interval = setInterval(() => {
            progress += 5;
            if (progress > 90) progress = 90;
            progressFill.style.width = progress + '%';
        }, 200);
        
        progressSection.dataset.interval = interval;
    }
}

function hideProgress() {
    const progressSection = document.getElementById('progressSection');
    const progressFill = document.getElementById('progressFill');

    if (progressSection) {
        const interval = progressSection.dataset.interval;
        if (interval) clearInterval(interval);
        
        progressFill.style.width = '100%';
        
        setTimeout(() => {
            progressSection.style.display = 'none';
            progressFill.style.width = '0%';
        }, 500);
    }
}

// Notification system
function showNotification(message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 1rem 1.5rem;
        background: ${type === 'success' ? '#28a745' : type === 'error' ? '#dc3545' : '#17a2b8'};
        color: white;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        z-index: 10000;
        animation: slideInRight 0.3s ease;
    `;
    notification.textContent = message;

    document.body.appendChild(notification);

    // Remove after 3 seconds
    setTimeout(() => {
        notification.style.animation = 'slideOutRight 0.3s ease';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// Filter functionality
function initializeFilters() {
    const severityFilter = document.getElementById('severityFilter');
    const categoryFilter = document.getElementById('categoryFilter');
    const searchFilter = document.getElementById('searchFilter');
    const clearFiltersBtn = document.getElementById('clearFiltersBtn');

    if (severityFilter) {
        severityFilter.addEventListener('change', applyFilters);
    }

    if (categoryFilter) {
        categoryFilter.addEventListener('change', applyFilters);
    }

    if (searchFilter) {
        searchFilter.addEventListener('input', applyFilters);
    }

    if (clearFiltersBtn) {
        clearFiltersBtn.addEventListener('click', clearFilters);
    }
}

function applyFilters() {
    const severityFilter = document.getElementById('severityFilter')?.value || 'all';
    const categoryFilter = document.getElementById('categoryFilter')?.value || 'all';
    const searchFilter = document.getElementById('searchFilter')?.value.toLowerCase() || '';

    let filtered = currentViolations.filter(violation => {
        const matchesSeverity = severityFilter === 'all' || violation.severity.toLowerCase() === severityFilter;
        const matchesCategory = categoryFilter === 'all' || violation.category.toLowerCase() === categoryFilter;
        const matchesSearch = !searchFilter || 
            violation.rule_name.toLowerCase().includes(searchFilter) ||
            violation.description.toLowerCase().includes(searchFilter) ||
            violation.file_path.toLowerCase().includes(searchFilter);

        return matchesSeverity && matchesCategory && matchesSearch;
    });

    // Update visible count
    const visibleCount = document.getElementById('visibleCount');
    if (visibleCount) {
        visibleCount.textContent = filtered.length;
    }

    // Re-populate table with filtered results
    populateViolationsTable(filtered);
}

function clearFilters() {
    const severityFilter = document.getElementById('severityFilter');
    const categoryFilter = document.getElementById('categoryFilter');
    const searchFilter = document.getElementById('searchFilter');

    if (severityFilter) severityFilter.value = 'all';
    if (categoryFilter) categoryFilter.value = 'all';
    if (searchFilter) searchFilter.value = '';

    applyFilters();
}

// View violation detail
function viewViolationDetail(index) {
    const violation = currentViolations[index];
    if (!violation) return;

    const modal = document.getElementById('violationModal');
    if (!modal) return;

    // Populate modal
    document.getElementById('modalTitle').textContent = violation.rule_name;
    document.getElementById('modalSeverity').textContent = violation.severity;
    document.getElementById('modalSeverity').className = `severity-badge severity-${violation.severity.toLowerCase()}`;
    document.getElementById('modalCategory').textContent = violation.category.toUpperCase();
    document.getElementById('modalRuleId').textContent = violation.rule_id;
    document.getElementById('modalFile').textContent = violation.file_path;
    document.getElementById('modalLine').textContent = violation.line_number;
    document.getElementById('modalDescription').textContent = violation.description;
    document.getElementById('modalRecommendation').textContent = violation.recommendation;
    document.getElementById('modalCodeSnippet').textContent = violation.code_snippet;

    // Show modal
    modal.style.display = 'block';

    // Setup modal buttons
    const modalFixBtn = document.getElementById('modalFixBtn');
    const modalChatBtn = document.getElementById('modalChatBtn');

    if (modalFixBtn) {
        modalFixBtn.onclick = () => {
            modal.style.display = 'none';
            remediateViolations([violation], false);
        };
    }

    if (modalChatBtn) {
        modalChatBtn.onclick = () => {
            sessionStorage.setItem('chatContext', JSON.stringify(violation));
            window.location.href = '/chat';
        };
    }
}

// Close modal
document.addEventListener('click', function(e) {
    if (e.target.classList.contains('modal-close')) {
        e.target.closest('.modal').style.display = 'none';
    }
    
    if (e.target.classList.contains('modal')) {
        e.target.style.display = 'none';
    }
});

// Add CSS animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideInRight {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    @keyframes slideOutRight {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(100%);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);

// Export functions for use in HTML
window.analyzeFile = analyzeFile;
window.viewViolationDetail = viewViolationDetail;

// Made with Bob
